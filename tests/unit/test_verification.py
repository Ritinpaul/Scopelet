"""
Unit and CLI tests for patch ingestion and private verification engine (Phase 15).
"""

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch

from apps.cli.main import app
from scopelet.capsule.models import CapsuleManifest, SolutionMetadata, SolutionVerification
from scopelet.runner import ExecutionResult
from scopelet.verification import (
    PatchApplier,
    PatchError,
    TestRunVerdict,
    VerificationEngine,
    VerificationReport,
)


cli_runner = CliRunner()


def test_verification_schema_validation():
    schema_path = Path("schemas/verification.schema.json")
    assert schema_path.exists()
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "verdict" in schema_data["properties"]
    assert "target_test" in schema_data["properties"]

    report = VerificationReport(
        schema_version="1.0",
        verdict="ACCEPTED",
        patch_hash="abc123patchhash",
        modified_files=["src/date.ts"],
        target_test=TestRunVerdict(
            command="npm test",
            passed=True,
            exit_code=0,
            duration_ms=45,
        ),
        compliance_passed=True,
        rejection_reasons=[],
        created_at="2026-10-18T12:00:00Z",
    )

    data = report.model_dump()
    assert data["verdict"] == "ACCEPTED"
    assert data["compliance_passed"] is True
    assert data["target_test"]["passed"] is True


def test_patch_applier_extract_files():
    patch_text = (
        "--- a/src/date.ts\n"
        "+++ b/src/date.ts\n"
        "@@ -1,3 +1,3 @@\n"
        "-export const a = 1;\n"
        "+export const a = 2;\n"
        "--- /dev/null\n"
        "+++ b/src/new_file.ts\n"
        "@@ -0,0 +1 @@\n"
        "+export const b = 3;\n"
        "--- a/src/old_file.ts\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-export const c = 4;\n"
    )

    files = PatchApplier.extract_modified_files(patch_text)
    assert files == ["src/date.ts", "src/new_file.ts", "src/old_file.ts"]


def test_patch_applier_apply_hunks(tmp_path: Path):
    target_dir = tmp_path / "repo"
    target_dir.mkdir()
    (target_dir / "src").mkdir()
    target_file = target_dir / "src" / "date.ts"
    target_file.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    patch_text = (
        "--- a/src/date.ts\n"
        "+++ b/src/date.ts\n"
        "@@ -1,3 +1,3 @@\n"
        " line 1\n"
        "-line 2\n"
        "+line 2 modified\n"
        " line 3\n"
    )

    modified = PatchApplier.apply_patch(patch_text, target_dir)
    assert modified == ["src/date.ts"]
    assert target_file.read_text(encoding="utf-8") == "line 1\nline 2 modified\nline 3\n"


def test_patch_applier_create_and_delete_file(tmp_path: Path):
    target_dir = tmp_path / "repo"
    target_dir.mkdir()
    (target_dir / "src").mkdir()
    del_file = target_dir / "src" / "to_delete.ts"
    del_file.write_text("goodbye\n", encoding="utf-8")

    patch_text = (
        "--- /dev/null\n"
        "+++ b/src/brand_new.ts\n"
        "@@ -0,0 +1 @@\n"
        "+hello world\n"
        "--- a/src/to_delete.ts\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-goodbye\n"
    )

    modified = PatchApplier.apply_patch(patch_text, target_dir)
    assert "src/brand_new.ts" in modified
    assert "src/to_delete.ts" in modified

    assert (target_dir / "src" / "brand_new.ts").exists()
    assert (target_dir / "src" / "brand_new.ts").read_text(encoding="utf-8") == "hello world\n"
    assert not del_file.exists()


def _setup_private_repo(tmp_path: Path) -> tuple[Path, CapsuleManifest]:
    repo = tmp_path / "private_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "date.ts").write_text("export const offset = 0;\n", encoding="utf-8")
    (repo / "src" / "timezone.ts").write_text("export const tz = 'UTC';\n", encoding="utf-8")
    (repo / "test").mkdir()
    (repo / "test" / "date.test.ts").write_text("it('works', () => {});\n", encoding="utf-8")

    manifest = CapsuleManifest(
        schema_version="1.0",
        capsule_hash="cap123",
        title="Timezone bug",
        created_at="2026-10-18T00:00:00Z",
        command="npm test",
        allowed_changes=["src/date.ts", "src/timezone.ts"],
        files=[],
    )
    return repo, manifest


def test_verification_engine_accepted(tmp_path: Path):
    repo, manifest = _setup_private_repo(tmp_path)

    sol_dir = tmp_path / "solution"
    sol_dir.mkdir()
    patch_file = sol_dir / "solution.patch"
    patch_file.write_text(
        "--- a/src/date.ts\n"
        "+++ b/src/date.ts\n"
        "@@ -1 +1 @@\n"
        "-export const offset = 0;\n"
        "+export const offset = 5.5;\n",
        encoding="utf-8",
    )

    mock_res = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th123",
        exit_code=0,
        stdout="All 10 tests passed",
        stderr="",
        duration_ms=45,
    )

    with patch("scopelet.runner.IsolatedRunner.run", return_value=mock_res):
        engine = VerificationEngine(repo_dir=repo)
        report = engine.verify_solution(
            solution_target=sol_dir,
            manifest_target=None,
            command="npm test",
        )

        assert report.verdict == "ACCEPTED"
        assert report.compliance_passed is True
        assert report.target_test.passed is True
        assert report.target_test.exit_code == 0
        assert len(report.rejection_reasons) == 0


def test_verification_engine_boundary_violation_rejected(tmp_path: Path):
    repo, manifest = _setup_private_repo(tmp_path)

    sol_dir = tmp_path / "solution"
    sol_dir.mkdir()
    patch_file = sol_dir / "solution.patch"
    patch_file.write_text(
        "--- a/test/date.test.ts\n"
        "+++ b/test/date.test.ts\n"
        "@@ -1 +1 @@\n"
        "-it('works', () => {});\n"
        "+// tampered\n",
        encoding="utf-8",
    )

    capsule_json = tmp_path / "capsule.json"
    capsule_json.write_text(manifest.model_dump_json(), encoding="utf-8")

    engine = VerificationEngine(repo_dir=repo)
    report = engine.verify_solution(
        solution_target=sol_dir,
        manifest_target=capsule_json,
    )

    assert report.verdict == "REJECTED"
    assert report.compliance_passed is False
    assert any("Unauthorized file modifications" in r for r in report.rejection_reasons)


def test_verification_engine_target_test_failed_rejected(tmp_path: Path):
    repo, manifest = _setup_private_repo(tmp_path)

    sol_dir = tmp_path / "solution"
    sol_dir.mkdir()
    patch_file = sol_dir / "solution.patch"
    patch_file.write_text(
        "--- a/src/date.ts\n"
        "+++ b/src/date.ts\n"
        "@@ -1 +1 @@\n"
        "-export const offset = 0;\n"
        "+export const offset = 99;\n",
        encoding="utf-8",
    )

    mock_res = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th123",
        exit_code=1,
        stdout="AssertionError: expected 5.5 received 99",
        stderr="",
        duration_ms=40,
    )

    with patch("scopelet.runner.IsolatedRunner.run", return_value=mock_res):
        engine = VerificationEngine(repo_dir=repo)
        report = engine.verify_solution(
            solution_target=sol_dir,
            command="npm test",
        )

        assert report.verdict == "REJECTED"
        assert report.target_test.passed is False
        assert any("Target test failed with exit code 1" in r for r in report.rejection_reasons)


def test_verification_engine_regression_suite(tmp_path: Path):
    repo, manifest = _setup_private_repo(tmp_path)

    sol_dir = tmp_path / "solution"
    sol_dir.mkdir()
    patch_file = sol_dir / "solution.patch"
    patch_file.write_text(
        "--- a/src/date.ts\n"
        "+++ b/src/date.ts\n"
        "@@ -1 +1 @@\n"
        "-export const offset = 0;\n"
        "+export const offset = 5.5;\n",
        encoding="utf-8",
    )

    target_pass = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th1",
        exit_code=0,
        stdout="Target test passed",
        stderr="",
        duration_ms=30,
    )
    reg_fail = ExecutionResult(
        command="npm run test:all",
        backend="local_sandbox",
        tree_hash="th2",
        exit_code=1,
        stdout="Regression failed in billing suite",
        stderr="",
        duration_ms=80,
    )

    with patch("scopelet.runner.IsolatedRunner.run", side_effect=[target_pass, reg_fail]):
        engine = VerificationEngine(repo_dir=repo)
        report = engine.verify_solution(
            solution_target=sol_dir,
            command="npm test",
            regression_cmd="npm run test:all",
        )

        assert report.verdict == "REJECTED"
        assert report.target_test.passed is True
        assert report.regression_test is not None
        assert report.regression_test.passed is False
        assert any("Regression test suite failed" in r for r in report.rejection_reasons)


def test_cli_verify_command(tmp_path: Path):
    repo, manifest = _setup_private_repo(tmp_path)

    sol_dir = tmp_path / "solution"
    sol_dir.mkdir()
    patch_file = sol_dir / "solution.patch"
    patch_file.write_text(
        "--- a/src/date.ts\n"
        "+++ b/src/date.ts\n"
        "@@ -1 +1 @@\n"
        "-export const offset = 0;\n"
        "+export const offset = 5.5;\n",
        encoding="utf-8",
    )

    mock_res = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th123",
        exit_code=0,
        stdout="Verification passed",
        stderr="",
        duration_ms=45,
    )

    with patch("scopelet.runner.IsolatedRunner.run", return_value=mock_res):
        # 1. Successful verification via root command
        res = cli_runner.invoke(
            app,
            ["verify", str(patch_file), "--repo", str(repo)],
        )
        assert res.exit_code == 0
        assert "ACCEPTED" in res.output
        assert "Candidate patch successfully verified and accepted" in res.output

        # 2. Capsule sub-typer command
        res_sub = cli_runner.invoke(
            app,
            ["capsule", "verify", str(sol_dir), "--repo", str(repo)],
        )
        assert res_sub.exit_code == 0
        assert "ACCEPTED" in res_sub.output

    # 3. Failing verification exits with code 1
    mock_fail = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th123",
        exit_code=1,
        stdout="Failure",
        stderr="Error",
        duration_ms=45,
    )
    with patch("scopelet.runner.IsolatedRunner.run", return_value=mock_fail):
        res_err = cli_runner.invoke(
            app,
            ["verify", str(patch_file), "--repo", str(repo)],
        )
        assert res_err.exit_code == 1
        assert "REJECTED" in res_err.output
