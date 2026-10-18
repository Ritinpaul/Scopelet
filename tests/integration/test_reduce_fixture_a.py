"""
Integration test for behavior-preserving reducer on Fixture A (Timezone Bug).
Verifies the Phase 7 verification gate requirements:
1. Capsule LOC < 10% of original
2. Failure fingerprint preserved exactly
3. Reducer evaluations < 200
"""

import tempfile
from pathlib import Path
import pytest

from scopelet.capture import capture
from scopelet.runner import IsolatedRunner
from scopelet.reducer import (
    CandidateState,
    ReducerOracle,
    DeltaDebuggingReducer,
    ReducerProgress,
)
from scopelet.analysis.static import TypeScriptAnalyzer
from scopelet.analysis.dynamic import DynamicTracer, compute_candidate_slice


@pytest.mark.integration
def test_reduce_fixture_a_preserves_failure_under_ten_percent_loc():
    fixture_dir = Path("fixtures/timezone-bug").resolve()
    assert fixture_dir.exists(), f"Fixture directory not found: {fixture_dir}"

    command = "npm test"

    # Step 1: Capture baseline failure and oracle fingerprint
    cap_result = capture(command=command, cwd=fixture_dir)
    expected_fp = cap_result.failure.fingerprint
    stack_frames = cap_result.failure.frames
    assert expected_fp, "Baseline failure fingerprint must not be empty"

    # Step 2: Initialize full repository candidate state
    initial_state = CandidateState.from_directory(fixture_dir)
    initial_loc = initial_state.loc()
    initial_files = initial_state.file_count()
    assert initial_loc > 500, f"Expected initial LOC > 500, got {initial_loc}"
    assert initial_files > 50, f"Expected initial files > 50, got {initial_files}"

    # Step 3: Compute candidate slice using static graph + dynamic trace
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_dir)
    tracer = DynamicTracer()
    report = tracer.trace(command, fixture_dir)
    slice_result = compute_candidate_slice(
        static_graph=graph,
        dynamic_trace=report.trace,
        stack_frames=stack_frames,
        all_files=set(graph.nodes.keys()),
    )
    slice_files = set(slice_result.combined_slice)
    assert len(slice_files) < initial_files, "Candidate slice must be smaller than repo files"

    # Step 4: Run delta-debugging reducer in isolated workspace
    temp_workspace = Path(tempfile.mkdtemp(prefix="scopelet_test_reduce_a_"))
    try:
        oracle = ReducerOracle(
            command=command,
            expected_fingerprint=expected_fp,
            workspace_dir=temp_workspace,
        )

        reducer = DeltaDebuggingReducer(
            oracle=oracle,
            progress=ReducerProgress(quiet=True),
            protected_files=set(stack_frames),
            max_evaluations=200,
        )

        final_state, summary = reducer.reduce(
            initial_state=initial_state,
            candidate_slice_files=slice_files,
        )

        # Gate Check 1: LOC reduction < 10% of original repository (<= 250 LOC out of ~2500)
        assert summary.final_loc <= 250, (
            f"Final LOC ({summary.final_loc}) exceeded threshold 250 LOC"
        )
        assert summary.final_files <= 15, (
            f"Final files ({summary.final_files}) exceeded threshold 15 files"
        )

        # Gate Check 2: Reducer evaluations < 200
        assert summary.total_evaluations < 200, (
            f"Reducer evaluations ({summary.total_evaluations}) exceeded threshold 200"
        )

        # Gate Check 3: Essential defect files retained
        assert "src/date/timezone.ts" in final_state.active_files
        assert "src/invoice/invoice.service.ts" in final_state.active_files
        assert "tests/invoice-timezone.test.ts" in final_state.active_files

        # Gate Check 4: Unrelated domains pruned
        assert not any(f.startswith("src/admin/") for f in final_state.active_files)
        assert not any(f.startswith("src/analytics/") for f in final_state.active_files)
        assert not any(f.startswith("src/notifications/") for f in final_state.active_files)

        # Gate Check 5: Materialized reduced capsule executes independently and matches fingerprint
        reduced_output_dir = Path(tempfile.mkdtemp(prefix="scopelet_reduced_capsule_"))
        final_state.materialize(reduced_output_dir, link_node_modules=True)

        runner = IsolatedRunner()
        exec_result = runner.run(command=command, cwd=reduced_output_dir, use_cache=False)

        assert exec_result.exit_code != 0, "Reduced reproduction must fail"
        assert exec_result.fingerprint == expected_fp, (
            f"Reduced capsule fingerprint {exec_result.fingerprint} does not match expected {expected_fp}"
        )

    finally:
        import shutil
        shutil.rmtree(temp_workspace, ignore_errors=True)
