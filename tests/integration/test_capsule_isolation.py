"""
Integration test for standalone capsule reproduction under repository isolation.
Verifies Phase 8 verification gate:
- Build self-contained .scopelet archive from reduced state
- Execute capsule in isolated workspace with source repository detached
- Confirms failure fingerprint matches original defect exactly
"""

import shutil
import tempfile
from pathlib import Path
import pytest

from scopelet.capture import capture
from scopelet.reducer import (
    CandidateState,
    ReducerOracle,
    DeltaDebuggingReducer,
    ReducerProgress,
)
from scopelet.analysis.static import TypeScriptAnalyzer
from scopelet.analysis.dynamic import DynamicTracer, compute_candidate_slice
from scopelet.capsule import CapsuleBuilder, CapsulePackager, CapsuleRunner


def test_standalone_capsule_reproduces_failure_without_source_repo():
    fixture_dir = Path("fixtures/timezone-bug").resolve()
    assert fixture_dir.exists(), f"Fixture directory not found: {fixture_dir}"

    command = "npm test"

    # Step 1: Baseline failure capture
    cap_result = capture(command=command, cwd=fixture_dir)
    expected_fp = cap_result.failure.fingerprint
    stack_frames = cap_result.failure.frames
    assert expected_fp, "Expected failure fingerprint must exist"

    # Step 2: Minimize repository to candidate slice and essential files
    initial_state = CandidateState.from_directory(fixture_dir)
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_dir)
    tracer = DynamicTracer()
    report = tracer.trace(command, fixture_dir)
    slice_res = compute_candidate_slice(
        static_graph=graph,
        dynamic_trace=report.trace,
        stack_frames=stack_frames,
        all_files=set(graph.nodes.keys()),
    )

    temp_reduction_ws = Path(tempfile.mkdtemp(prefix="scopelet_iso_ws_"))
    try:
        oracle = ReducerOracle(
            command=command,
            expected_fingerprint=expected_fp,
            workspace_dir=temp_reduction_ws,
        )
        reducer = DeltaDebuggingReducer(
            oracle=oracle,
            progress=ReducerProgress(quiet=True),
            protected_files=set(stack_frames),
            max_evaluations=200,
        )
        reduced_state, summary = reducer.reduce(
            initial_state=initial_state,
            candidate_slice_files=set(slice_res.combined_slice),
        )

        # Step 3: Assemble capsule directory and package into .scopelet archive
        capsule_staging = Path(tempfile.mkdtemp(prefix="scopelet_capsule_stage_"))
        builder = CapsuleBuilder()
        manifest = builder.build(
            output_dir=capsule_staging,
            state=reduced_state,
            title="Invoice Timezone Offset Bug",
            command=command,
            failure_fingerprint=expected_fp,
        )

        archive_file = Path(tempfile.mktemp(suffix=".scopelet"))
        CapsulePackager.pack(capsule_staging, archive_file)
        assert archive_file.exists()
        assert archive_file.stat().st_size > 0

        # Step 4: Standalone test: copy .scopelet archive to isolated directory
        isolated_dir = Path(tempfile.mkdtemp(prefix="scopelet_isolated_run_"))
        isolated_capsule = isolated_dir / "invoice.scopelet"
        shutil.copy(archive_file, isolated_capsule)

        # Step 5: Execute capsule standalone with runner
        capsule_runner = CapsuleRunner()
        parsed_manifest, exec_result = capsule_runner.run(
            capsule_target=isolated_capsule,
            dependency_dir=fixture_dir,
        )

        # Verifications
        assert exec_result.exit_code != 0, "Execution under isolation must fail"
        assert exec_result.fingerprint == expected_fp, (
            f"Standalone fingerprint ({exec_result.fingerprint}) did not match expected ({expected_fp})"
        )
        assert parsed_manifest.capsule_hash == manifest.capsule_hash

    finally:
        shutil.rmtree(temp_reduction_ws, ignore_errors=True)
