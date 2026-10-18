"""
End-to-End Pipeline Integration Test (Phase 20).
Validates complete lifecycle from capture to verification and reintegration on timezone-bug fixture:
capture -> slice -> reduce -> sanitize -> export -> solve -> hidden verify -> reintegrate.
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


def test_full_lifecycle_pipeline_e2e():
    """
    Executes the complete 8-phase Scopelet lifecycle pipeline on fixtures/timezone-bug.
    """
    fixture_dir = Path("fixtures/timezone-bug").resolve()
    assert fixture_dir.exists(), f"Fixture directory not found: {fixture_dir}"

    test_cmd = "npm test"

    # Step 1: Capture baseline defect and extract failure fingerprint
    cap_res = capture(command=test_cmd, cwd=fixture_dir)
    expected_fp = cap_res.failure.fingerprint
    stack_frames = cap_res.failure.frames
    assert expected_fp, "Captured failure fingerprint must not be empty"

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
    temp_reducer_ws = Path(tempfile.mkdtemp(prefix="scopelet_e2e_reduce_"))
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
        temp_sanitize_ws = Path(tempfile.mkdtemp(prefix="scopelet_e2e_sanitize_"))
        reduced_state.materialize(temp_sanitize_ws)
        sanitizer = BehaviorPreservingSanitizer(
            workspace_dir=temp_sanitize_ws,
            command=test_cmd,
            expected_fingerprint=expected_fp,
            strict_type_check=False,
        )
        mapping_store = sanitizer.auto_sanitize()
        assert (temp_sanitize_ws / ".scopelet" / "private" / "mapping.json").exists()

        # Step 5: Package into standalone .scopelet capsule archive
        capsule_stage = Path(tempfile.mkdtemp(prefix="scopelet_e2e_capsule_"))
        builder = CapsuleBuilder()
        builder.build(
            output_dir=capsule_stage,
            state=reduced_state,
            title="Timezone Format Defect",
            command=test_cmd,
            failure_fingerprint=expected_fp,
        )
        archive_file = Path(tempfile.mktemp(suffix=".scopelet"))
        CapsulePackager.pack(capsule_stage, archive_file)
        assert archive_file.exists()

        # Verify privacy scan on packaged archive: no critical leaks
        scanner = PrivacyScanner()
        scan_report = scanner.scan(archive_file)
        critical_leaks = [f for f in scan_report.findings if f.severity == "CRITICAL"]
        assert len(critical_leaks) == 0

        # Step 6: External solver generates candidate bug fix patch
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

        # Step 7: Anti-cheating boundary check (Phase 19)
        boundary_checker = BoundaryChecker()
        assert boundary_checker.is_valid(genuine_patch), "Genuine patch must pass all boundary checks"

        # Step 8: Private hidden verifier oracle evaluation
        verifier = PrivateHiddenVerifier(
            repo_dir=fixture_dir,
            hidden_regression_cmd="npm run test:hidden",
            full_suite_cmd="npm run test:all",
        )
        verify_report = verifier.verify(
            solution_patch=genuine_patch,
            target_cmd="npm run test:invoice",
            hidden_regression_cmd="npm run test:hidden",
        )
        assert verify_report.verdict == Verdict.ACCEPT
        assert len(verify_report.rejection_reasons) == 0
        assert verify_report.target_test.passed
        assert verify_report.hidden_regression_test.passed

    finally:
        shutil.rmtree(temp_reducer_ws, ignore_errors=True)


def test_pipeline_adversarial_cheat_blocked_before_reintegration():
    """
    Verifies that adversarial cheat patches are blocked at the verification gate
    and cannot be reintegrated into the repository.
    """
    fixture_dir = Path("fixtures/timezone-bug").resolve()

    # Adversarial cheat 1: Modify package.json scripts to bypass tests
    cheat_package_json = (
        "--- a/package.json\n"
        "+++ b/package.json\n"
        "@@ -7,3 +7,3 @@\n"
        "-    \"test\": \"vitest run\",\n"
        "+    \"test\": \"echo SUCCESS\",\n"
    )

    boundary_checker = BoundaryChecker()
    assert not boundary_checker.is_valid(cheat_package_json)

    # Adversarial cheat 2: Hardcode answer for visible repro test
    cheat_hardcoded = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -15,5 +15,3 @@\n"
        " export function formatToTimezoneDate(date: Date, timezone: string = DEFAULT_TIMEZONE): string {\n"
        "-  const year = date.getUTCFullYear();\n"
        "+  return '2026-10-18'; // Cheat: hardcoded to pass visible test only\n"
        " }\n"
    )

    verifier = PrivateHiddenVerifier(
        repo_dir=fixture_dir,
        hidden_regression_cmd="npm run test:hidden",
    )
    report = verifier.verify(
        solution_patch=cheat_hardcoded,
        target_cmd="npm run test:invoice",
        hidden_regression_cmd="npm run test:hidden",
    )

    assert report.verdict == Verdict.REJECT
    assert any("Hidden regression test suite failed" in r for r in report.rejection_reasons)

    # Confirm verifier rejects package.json modifications
    report_pkg = verifier.verify(cheat_package_json)
    assert report_pkg.verdict == Verdict.REJECT
    assert any("Configuration Integrity Policy" in r for r in report_pkg.rejection_reasons)

    # Confirm applier rejects patches targeting non-existent files
    invalid_patch = (
        "--- a/nonexistent_file.ts\n"
        "+++ b/nonexistent_file.ts\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )
    applier = SemanticPatchApplierV2(repo_dir=fixture_dir)
    res = applier.apply(invalid_patch)
    assert not res.success
