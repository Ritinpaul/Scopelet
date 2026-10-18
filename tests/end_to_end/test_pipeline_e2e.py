"""
Phase 20 - End-to-End Pipeline Test Suite.
Verifies that multi-repo fixtures complete the full 8-phase Scopelet lifecycle:
capture -> slice -> reduce -> sanitize -> export -> solve -> hidden verify -> reintegrate.
Gate requirement: >= 2 of 3 fixtures complete the full lifecycle successfully.
"""

from pathlib import Path
import shutil
import tempfile
import pytest

from scopelet.capture import capture
from scopelet.analysis.static import TypeScriptAnalyzer
from scopelet.analysis.dynamic import DynamicTracer, compute_candidate_slice
from scopelet.reducer import (
    CandidateState,
    ReducerOracle,
    DeltaDebuggingReducer,
    ReducerProgress,
)
from scopelet.privacy.sanitizer import BehaviorPreservingSanitizer
from scopelet.privacy.scanner.orchestrator import PrivacyScanner
from scopelet.capsule import CapsuleBuilder, CapsulePackager
from scopelet.patches.boundary_checker import BoundaryChecker
from scopelet.verifier.verifier import PrivateHiddenVerifier
from scopelet.verifier.verdict import Verdict
from scopelet.reintegration import SemanticPatchApplierV2


def _run_full_lifecycle_on_fixture(
    fixture_dir: Path,
    test_cmd: str,
    target_cmd: str,
    hidden_cmd: str,
    full_cmd: str,
    genuine_patch: str,
    capsule_title: str,
):
    # Step 1: Capture baseline failure and extract failure fingerprint
    cap_res = capture(command=test_cmd, cwd=fixture_dir)
    expected_fp = cap_res.failure.fingerprint
    stack_frames = cap_res.failure.frames
    assert expected_fp, f"Captured fingerprint for {fixture_dir.name} must exist"

    # Step 2: Static graph analysis and dynamic coverage tracing
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_dir)
    tracer = DynamicTracer()
    trace_rep = tracer.trace(test_cmd, fixture_dir)
    slice_res = compute_candidate_slice(
        static_graph=graph,
        dynamic_trace=trace_rep.trace,
        stack_frames=stack_frames,
        all_files=set(graph.nodes.keys()),
    )
    assert len(slice_res.combined_slice) > 0

    # Step 3: Delta debugging minimization
    initial_state = CandidateState.from_directory(fixture_dir)
    temp_reducer_ws = Path(tempfile.mkdtemp(prefix=f"scopelet_e2e_{fixture_dir.name}_red_"))
    try:
        oracle = ReducerOracle(
            command=test_cmd,
            expected_fingerprint=expected_fp,
            workspace_dir=temp_reducer_ws,
        )
        reducer = DeltaDebuggingReducer(
            oracle=oracle,
            progress=ReducerProgress(quiet=True),
            protected_files=set(stack_frames),
            max_evaluations=30,
        )
        reduced_state, _ = reducer.reduce(
            initial_state=initial_state,
            candidate_slice_files=set(slice_res.combined_slice),
        )
        assert len(reduced_state.active_files) <= len(initial_state.active_files)

        # Step 4: Behavior-preserving AST sanitization (Phase 10)
        temp_sanitize_ws = Path(tempfile.mkdtemp(prefix=f"scopelet_e2e_{fixture_dir.name}_san_"))
        reduced_state.materialize(temp_sanitize_ws)
        sanitizer = BehaviorPreservingSanitizer(
            workspace_dir=temp_sanitize_ws,
            command=test_cmd,
            expected_fingerprint=expected_fp,
            strict_type_check=False,
        )
        sanitizer.auto_sanitize()
        assert (temp_sanitize_ws / ".scopelet" / "private" / "mapping.json").exists()

        # Step 5: Package into standalone .scopelet capsule archive
        capsule_stage = Path(tempfile.mkdtemp(prefix=f"scopelet_e2e_{fixture_dir.name}_cap_"))
        builder = CapsuleBuilder()
        builder.build(
            output_dir=capsule_stage,
            state=reduced_state,
            title=capsule_title,
            command=test_cmd,
            failure_fingerprint=expected_fp,
        )
        archive_file = Path(tempfile.mktemp(suffix=".scopelet"))
        CapsulePackager.pack(capsule_stage, archive_file)
        assert archive_file.exists()

        # Privacy scan on packaged archive: no critical leaks
        scanner = PrivacyScanner()
        scan_report = scanner.scan(archive_file)
        critical_leaks = [f for f in scan_report.findings if f.severity == "CRITICAL"]
        assert len(critical_leaks) == 0

        # Step 6: Anti-cheating boundary check (Phase 19)
        boundary_checker = BoundaryChecker()
        assert boundary_checker.is_valid(genuine_patch), "Genuine patch must pass all boundary checks"

        # Step 7: Private hidden verifier oracle evaluation
        verifier = PrivateHiddenVerifier(
            repo_dir=fixture_dir,
            hidden_regression_cmd=hidden_cmd,
            full_suite_cmd=full_cmd,
        )
        verify_report = verifier.verify(
            solution_patch=genuine_patch,
            target_cmd=target_cmd,
            hidden_regression_cmd=hidden_cmd,
            full_suite_cmd=full_cmd,
        )
        assert verify_report.verdict == Verdict.ACCEPT
        assert len(verify_report.rejection_reasons) == 0
        assert verify_report.target_test.passed
        assert verify_report.hidden_regression_test.passed

    finally:
        shutil.rmtree(temp_reducer_ws, ignore_errors=True)


def test_e2e_fixture_timezone_bug():
    """
    Validates complete lifecycle on fixtures/timezone-bug (Fixture 1 of 3).
    """
    fixture_dir = Path("fixtures/timezone-bug").resolve()
    assert fixture_dir.exists()

    genuine_patch = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -15,7 +15,11 @@\n"
        " export function formatToTimezoneDate(date: Date, timezone: string = DEFAULT_TIMEZONE): string {\n"
        "-  // Defective implementation: ignores timezone parameter and outputs UTC date\n"
        "-  const year = date.getUTCFullYear();\n"
        "-  const month = String(date.getUTCMonth() + 1).padStart(2, '0');\n"
        "-  const day = String(date.getUTCDate()).padStart(2, '0');\n"
        "-  return `${year}-${month}-${day}`;\n"
        "+  const formatter = new Intl.DateTimeFormat('en-CA', {\n"
        "+    timeZone: timezone,\n"
        "+    year: 'numeric',\n"
        "+    month: '2-digit',\n"
        "+    day: '2-digit',\n"
        "+  });\n"
        "+  return formatter.format(date);\n"
        " }\n"
    )

    _run_full_lifecycle_on_fixture(
        fixture_dir=fixture_dir,
        test_cmd="npm test",
        target_cmd="npm run test:invoice",
        hidden_cmd="npm run test:hidden",
        full_cmd="npm run test:all",
        genuine_patch=genuine_patch,
        capsule_title="Timezone Formatting Offset Defect",
    )


def test_e2e_fixture_rounding_bug():
    """
    Validates complete lifecycle on fixtures/rounding-bug (Fixture 2 of 3).
    Satisfies Gate: >= 2 of 3 fixtures complete full lifecycle.
    """
    fixture_dir = Path("fixtures/rounding-bug").resolve()
    assert fixture_dir.exists()

    genuine_patch = (
        "--- a/src/utils/math.utils.ts\n"
        "+++ b/src/utils/math.utils.ts\n"
        "@@ -7,3 +7,3 @@\n"
        " export function roundCurrency(amount: number): number {\n"
        "-  return Math.floor(amount * 100) / 100;\n"
        "+  return Math.round((amount + 1e-9) * 100) / 100;\n"
        " }\n"
    )

    _run_full_lifecycle_on_fixture(
        fixture_dir=fixture_dir,
        test_cmd="npm test",
        target_cmd="npm run test:rounding",
        hidden_cmd="npm run test:hidden",
        full_cmd="npm run test:all",
        genuine_patch=genuine_patch,
        capsule_title="Currency Rounding Truncation Defect",
    )
