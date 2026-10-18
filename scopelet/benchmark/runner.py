"""
Benchmark runner executing pipeline reductions, recording telemetry and computing verification metrics.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import BenchmarkResult, BenchmarkSuite, count_loc_in_files
from ..capture.runner import capture
from ..patches.boundary_checker import BoundaryChecker
from ..reducer import CandidateState, DeltaDebuggingReducer, ReducerOracle, ReducerProgress
from ..reintegration import ReintegrationApplierV1
from ..verifier import PrivateHiddenVerifier, Verdict


class BenchmarkRunner:
    """
    Executes automated benchmark evaluations across test cases and records precision metrics.
    """

    def __init__(self, suite_name: str = "Scopelet Minimization Benchmark"):
        self.suite_name = suite_name

    def run_case(
        self,
        bug_id: str,
        fixture_dir: Path,
        test_cmd: str = "npm test",
        target_cmd: Optional[str] = None,
        hidden_cmd: Optional[str] = None,
        full_cmd: Optional[str] = None,
        genuine_patch: Optional[str] = None,
        candidate_slice_files: Optional[List[str]] = None,
        temp_work_dir: Optional[Path] = None,
    ) -> BenchmarkResult:
        """
        Runs complete benchmark evaluation for a single defect fixture.
        """
        fixture = fixture_dir.resolve()
        start_time = time.perf_counter()

        # 1. Capture target failure and fingerprint
        cap_result = capture(command=test_cmd, cwd=fixture)
        target_fingerprint = cap_result.failure.fingerprint
        stack_frames = cap_result.failure.frames

        # 2. File discovery and initial LOC computation
        initial_state = CandidateState.from_directory(fixture)
        all_files = sorted(list(initial_state.active_files))
        original_files_count = len(all_files)
        original_loc = count_loc_in_files(fixture, all_files)

        # 3. Delta-debugging reduction
        temp_dir = temp_work_dir or Path(tempfile.mkdtemp(prefix=f"scopelet_bench_{fixture.name}_"))
        cleanup_temp = temp_work_dir is None

        try:
            oracle = ReducerOracle(
                command=test_cmd,
                expected_fingerprint=target_fingerprint,
                workspace_dir=temp_dir,
            )
            reducer = DeltaDebuggingReducer(
                oracle=oracle,
                progress=ReducerProgress(quiet=True),
                protected_files=set(stack_frames),
                max_evaluations=50,
            )

            slice_set = set(candidate_slice_files) if candidate_slice_files else None
            reduced_state, reduction_stats = reducer.reduce(
                initial_state=initial_state,
                candidate_slice_files=slice_set,
            )

            generation_time_s = time.perf_counter() - start_time
            evaluations_count = reduction_stats.total_evaluations
            capsule_files_list = sorted(list(reduced_state.active_files))
            capsule_files_count = len(capsule_files_list)
            capsule_loc = count_loc_in_files(fixture, capsule_files_list)
            failure_preserved = True

            if original_loc > 0:
                reduction_pct = max(0.0, (1.0 - (capsule_loc / original_loc)) * 100.0)
            else:
                reduction_pct = 0.0

        finally:
            if cleanup_temp:
                shutil.rmtree(temp_dir, ignore_errors=True)

        # 4. Patch reintegration and hidden verification if genuine patch provided
        reintegration_success = False
        hidden_tests_passed = False

        if genuine_patch:
            # Boundary check
            boundary_checker = BoundaryChecker()
            boundary_valid = boundary_checker.is_valid(genuine_patch)

            if boundary_valid:
                if hidden_cmd and full_cmd:
                    verifier = PrivateHiddenVerifier(
                        repo_dir=fixture,
                        hidden_regression_cmd=hidden_cmd,
                        full_suite_cmd=full_cmd,
                    )
                    v_report = verifier.verify(
                        solution_patch=genuine_patch,
                        target_cmd=target_cmd or test_cmd,
                        hidden_regression_cmd=hidden_cmd,
                        full_suite_cmd=full_cmd,
                    )
                    reintegration_success = v_report.target_test.passed
                    hidden_tests_passed = (v_report.verdict == Verdict.ACCEPT)
                else:
                    reintegrator = ReintegrationApplierV1(repo_dir=fixture)
                    reint_result = reintegrator.apply(patch_content=genuine_patch)
                    reintegration_success = reint_result.success
                    hidden_tests_passed = reint_result.success

        return BenchmarkResult(
            bug_id=bug_id,
            fixture_name=fixture.name,
            original_files=original_files_count,
            original_loc=original_loc,
            capsule_files=capsule_files_count,
            capsule_loc=capsule_loc,
            reduction_pct=round(reduction_pct, 2),
            reducer_evaluations=evaluations_count,
            generation_time_s=round(generation_time_s, 2),
            failure_preserved=failure_preserved,
            reintegration_success=reintegration_success,
            hidden_tests_passed=hidden_tests_passed,
        )

    def run_suite(self, test_cases: List[Dict[str, Any]]) -> BenchmarkSuite:
        """
        Executes benchmark evaluations for a collection of test cases.
        """
        suite = BenchmarkSuite(suite_name=self.suite_name)
        for tc in test_cases:
            res = self.run_case(**tc)
            suite.add_result(res)
        return suite
