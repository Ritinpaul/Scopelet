"""
Unit and CLI tests for candidate solution patch creation and submission engine (Phase 14).
"""

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch

from apps.cli.main import app
from scopelet.capsule.models import CapsuleManifest, SolutionMetadata, SolutionVerification
from scopelet.capsule.builder import CapsuleBuilder
from scopelet.capsule.packager import CapsulePackager
from scopelet.capsule.solver import CapsuleSolver
from scopelet.capsule.submission import (
    SubmissionEngine,
    SubmissionError,
    UnauthorizedModificationError,
    VerificationError,
)
from scopelet.reducer.candidate import CandidateState
from scopelet.runner import ExecutionResult


cli_runner = CliRunner()


def test_solution_schema_validation():
    schema_path = Path("schemas/solution.schema.json")
    assert schema_path.exists()
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "properties" in schema_data
    assert "capsule_hash" in schema_data["properties"]
    assert "patch_hash" in schema_data["properties"]

    meta = SolutionMetadata(
        schema_version="1.0",
        capsule_hash="cap_hash_123",
        patch_hash="patch_hash_456",
        modified_files=["src/date.ts"],
        created_at="2026-10-18T12:00:00Z",
        author="Ritinpaul",
        verification=SolutionVerification(
            command="npm test",
            exit_code=0,
            success=True,
            duration_ms=42,
        ),
        summary="Fixed Asia/Kolkata date offset bug",
    )

    dumped = meta.model_dump()
    assert dumped["capsule_hash"] == "cap_hash_123"
    assert dumped["verification"]["success"] is True


def _create_test_capsule_workspace(tmp_path: Path) -> Path:
    source = tmp_path / "raw_capsule"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "date.ts").write_text("export const offset = 0;\n", encoding="utf-8")
    (source / "src" / "timezone.ts").write_text("export const tz = 'UTC';\n", encoding="utf-8")
    (source / "test").mkdir()
    (source / "test" / "date.test.ts").write_text("it('tests', () => {});\n", encoding="utf-8")

    state = CandidateState.from_directory(source)
    staging = tmp_path / "staging"
    builder = CapsuleBuilder()
    builder.build(
        output_dir=staging,
        state=state,
        title="Timezone bug",
        command="npm test",
        failure_fingerprint="fp_123",
        allowed_changes=["src/date.ts", "src/timezone.ts"],
    )

    archive = tmp_path / "test.scopelet"
    CapsulePackager.pack(staging, archive)

    dest = tmp_path / "workspace"
    CapsuleSolver.open_capsule(archive, extract_to=dest)
    return dest


def test_submission_engine_patch_generation(tmp_path: Path):
    ws = _create_test_capsule_workspace(tmp_path)

    # Modify allowed file
    (ws / "src" / "date.ts").write_text("export const offset = 5.5;\n", encoding="utf-8")

    engine = SubmissionEngine(workspace_dir=ws)
    patch_text = engine.generate_patch(["src/date.ts"])

    assert "--- a/src/date.ts" in patch_text
    assert "+++ b/src/date.ts" in patch_text
    assert "-export const offset = 0;" in patch_text
    assert "+export const offset = 5.5;" in patch_text


def test_submission_engine_creates_submission(tmp_path: Path):
    ws = _create_test_capsule_workspace(tmp_path)
    (ws / "src" / "date.ts").write_text("export const offset = 5.5;\n", encoding="utf-8")

    mock_manifest = CapsuleManifest.model_validate(
        json.loads((ws / "capsule.json").read_text(encoding="utf-8"))
    )
    mock_res = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th123",
        exit_code=0,
        stdout="All tests passed",
        stderr="",
        duration_ms=50,
    )

    with patch("scopelet.capsule.runner.CapsuleRunner.run", return_value=(mock_manifest, mock_res)):
        engine = SubmissionEngine(workspace_dir=ws)
        result = engine.create_submission(
            author="Ritinpaul",
            summary="Fixed timezone offset",
            verify=True,
        )

        assert result.is_compliant is True
        assert result.verified is True
        assert result.modified_files == ["src/date.ts"]
        assert Path(result.patch_file).exists()
        assert Path(result.metadata_file).exists()

        # Check solution.json contents
        meta_data = json.loads(Path(result.metadata_file).read_text(encoding="utf-8"))
        assert meta_data["author"] == "Ritinpaul"
        assert meta_data["summary"] == "Fixed timezone offset"
        assert meta_data["verification"]["success"] is True
        assert meta_data["verification"]["exit_code"] == 0


def test_submission_engine_rejects_unauthorized_modifications(tmp_path: Path):
    ws = _create_test_capsule_workspace(tmp_path)
    (ws / "src" / "date.ts").write_text("export const offset = 5.5;\n", encoding="utf-8")
    (ws / "test" / "date.test.ts").write_text("// cheating\n", encoding="utf-8")

    engine = SubmissionEngine(workspace_dir=ws)
    with pytest.raises(UnauthorizedModificationError, match="Unauthorized modifications detected"):
        engine.create_submission(verify=False)


def test_submission_engine_rejects_no_edits(tmp_path: Path):
    ws = _create_test_capsule_workspace(tmp_path)
    engine = SubmissionEngine(workspace_dir=ws)

    with pytest.raises(SubmissionError, match="No modifications detected in allowed files"):
        engine.create_submission(verify=False)


def test_submission_engine_rejects_failed_verification(tmp_path: Path):
    ws = _create_test_capsule_workspace(tmp_path)
    (ws / "src" / "date.ts").write_text("export const offset = 5.5;\n", encoding="utf-8")

    mock_manifest = CapsuleManifest.model_validate(
        json.loads((ws / "capsule.json").read_text(encoding="utf-8"))
    )
    mock_res = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th123",
        exit_code=1,
        stdout="Test assertion error",
        stderr="",
        duration_ms=45,
    )

    with patch("scopelet.capsule.runner.CapsuleRunner.run", return_value=(mock_manifest, mock_res)):
        engine = SubmissionEngine(workspace_dir=ws)
        with pytest.raises(VerificationError, match="failed with exit code 1"):
            engine.create_submission(verify=True)


def test_submission_engine_skip_verify(tmp_path: Path):
    ws = _create_test_capsule_workspace(tmp_path)
    (ws / "src" / "date.ts").write_text("export const offset = 5.5;\n", encoding="utf-8")

    engine = SubmissionEngine(workspace_dir=ws)
    result = engine.create_submission(verify=False)
    assert result.verified is False
    assert result.metadata.verification is None


def test_cli_submit_command(tmp_path: Path):
    ws = _create_test_capsule_workspace(tmp_path)
    (ws / "src" / "date.ts").write_text("export const offset = 5.5;\n", encoding="utf-8")

    mock_manifest = CapsuleManifest.model_validate(
        json.loads((ws / "capsule.json").read_text(encoding="utf-8"))
    )
    mock_res = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="th123",
        exit_code=0,
        stdout="PASS",
        stderr="",
        duration_ms=30,
    )

    with patch("scopelet.capsule.runner.CapsuleRunner.run", return_value=(mock_manifest, mock_res)):
        # 1. Test root submit command
        res = cli_runner.invoke(
            app,
            ["submit", "--dir", str(ws), "--author", "Ritinpaul", "--message", "Fix bug"],
        )
        assert res.exit_code == 0
        assert "solution.patch" in res.output
        assert "solution.json" in res.output
        assert "Candidate solution successfully packaged" in res.output

        # 2. Test capsule submit command with --skip-verify
        res_capsule = cli_runner.invoke(
            app,
            ["capsule", "submit", "--dir", str(ws), "--skip-verify"],
        )
        assert res_capsule.exit_code == 0
        assert "Verification tests were skipped" in res_capsule.output

    # 3. Test unauthorized edit failure via CLI
    (ws / "test" / "date.test.ts").write_text("tampered", encoding="utf-8")
    res_fail = cli_runner.invoke(app, ["submit", "--dir", str(ws)])
    assert res_fail.exit_code == 1
    assert "Unauthorized modification" in res_fail.output
