"""
Unit and CLI tests for External Solver Mode (Phase 13).
Verifies capsule opening, status checking, and solver commands.
"""

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from unittest.mock import MagicMock, patch

from apps.cli.main import app
from scopelet.capsule.models import CapsuleFile, CapsuleManifest
from scopelet.capsule.packager import CapsulePackager
from scopelet.capsule.builder import CapsuleBuilder
from scopelet.capsule.solver import CapsuleSolver, SolverStatus
from scopelet.reducer.candidate import CandidateState
from scopelet.runner import ExecutionResult


runner = CliRunner()


def test_solver_open_display_formatting():
    manifest = CapsuleManifest(
        schema_version="1.0",
        capsule_hash="hash123",
        title="Invoice date is incorrect for Asia/Kolkata.",
        created_at="2026-10-18T00:00:00Z",
        command="npm test",
        failure_description="Expected 2026-10-18, Received 2026-10-17",
        allowed_changes=["src/date.ts", "src/timezone.ts"],
        files=[],
    )

    display = CapsuleSolver.get_open_display(manifest)
    lines = display.strip().splitlines()

    assert len(lines) == 4
    assert lines[0] == "Task:     Invoice date is incorrect for Asia/Kolkata."
    assert lines[1] == "Run:      npm test"
    assert lines[2] == "Failure:  Expected 2026-10-18, Received 2026-10-17"
    assert lines[3] == "Editable: src/date.ts, src/timezone.ts"


def test_solver_open_archive(tmp_path: Path):
    source = tmp_path / "capsule_src"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "date.ts").write_text("export const d = 1;", encoding="utf-8")
    (source / "src" / "timezone.ts").write_text("export const tz = 'UTC';", encoding="utf-8")
    (source / "test").mkdir()
    (source / "test" / "date.test.ts").write_text("it('works', () => {});", encoding="utf-8")

    state = CandidateState.from_directory(source)
    staging = tmp_path / "staging"
    builder = CapsuleBuilder()
    manifest = builder.build(
        output_dir=staging,
        state=state,
        title="Timezone bug",
        command="npm test",
        failure_fingerprint="fp_tz_1",
        failure_description="Expected 2026-10-18, Received 2026-10-17",
        allowed_changes=["src/date.ts", "src/timezone.ts"],
    )

    archive = tmp_path / "test_capsule.scopelet"
    CapsulePackager.pack(staging, archive)

    dest_dir = tmp_path / "extracted_ws"
    man_opened, extracted_dir, display_text = CapsuleSolver.open_capsule(archive, extract_to=dest_dir)

    assert extracted_dir == dest_dir
    assert (extracted_dir / "capsule.json").exists()
    assert (extracted_dir / "src" / "date.ts").exists()
    assert man_opened.title == "Timezone bug"
    assert man_opened.failure_description == "Expected 2026-10-18, Received 2026-10-17"
    assert "Task:     Timezone bug" in display_text
    assert "Editable: src/date.ts, src/timezone.ts" in display_text


def test_solver_status_compliance(tmp_path: Path):
    ws = tmp_path / "solver_workspace"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "date.ts").write_text("export const date = 1;", encoding="utf-8")
    (ws / "src" / "timezone.ts").write_text("export const tz = 'UTC';", encoding="utf-8")
    (ws / "test").mkdir()
    (ws / "test" / "date.test.ts").write_text("it('tests', () => {});", encoding="utf-8")

    state = CandidateState.from_directory(ws)
    builder = CapsuleBuilder()
    builder.build(
        output_dir=ws,
        state=state,
        title="Invoice date bug",
        command="npm test",
        failure_fingerprint="fp_inv",
        allowed_changes=["src/date.ts", "src/timezone.ts"],
    )

    # 1. Initially untouched: compliant
    status = CapsuleSolver.get_status(ws)
    assert status.is_compliant is True
    assert status.modified_allowed == []
    assert status.modified_forbidden == []
    assert status.added_files == []
    assert status.deleted_files == []
    assert status.untouched_allowed == ["src/date.ts", "src/timezone.ts"]
    assert "Compliance: PASS" in status.format_text()

    # 2. Modify allowed file: still compliant
    (ws / "src" / "date.ts").write_text("export const date = 2;", encoding="utf-8")
    status = CapsuleSolver.get_status(ws)
    assert status.is_compliant is True
    assert status.modified_allowed == ["src/date.ts"]
    assert status.untouched_allowed == ["src/timezone.ts"]

    # 3. Modify forbidden file: non-compliant
    (ws / "test" / "date.test.ts").write_text("it('cheating', () => {});", encoding="utf-8")
    status = CapsuleSolver.get_status(ws)
    assert status.is_compliant is False
    assert status.modified_forbidden == ["test/date.test.ts"]
    assert "Compliance: FAIL" in status.format_text()

    # Revert forbidden edit
    (ws / "test" / "date.test.ts").write_text("it('tests', () => {});", encoding="utf-8")

    # 4. Add unexpected new file: non-compliant
    (ws / "src" / "extra.ts").write_text("extra", encoding="utf-8")
    status = CapsuleSolver.get_status(ws)
    assert status.is_compliant is False
    assert status.added_files == ["src/extra.ts"]

    # Remove extra file
    (ws / "src" / "extra.ts").unlink()

    # 5. Delete existing file: non-compliant
    (ws / "src" / "timezone.ts").unlink()
    status = CapsuleSolver.get_status(ws)
    assert status.is_compliant is False
    assert status.deleted_files == ["src/timezone.ts"]


def test_cli_capsule_open_and_status(tmp_path: Path):
    source = tmp_path / "src_capsule"
    source.mkdir()
    (source / "src").mkdir()
    (source / "src" / "date.ts").write_text("console.log('original');", encoding="utf-8")
    (source / "test").mkdir()
    (source / "test" / "date.test.ts").write_text("it('fails', () => {});", encoding="utf-8")

    state = CandidateState.from_directory(source)
    staging = tmp_path / "staging"
    builder = CapsuleBuilder()
    builder.build(
        output_dir=staging,
        state=state,
        title="CLI Capsule Open Test",
        command="npm test",
        failure_fingerprint="fp_cli_1",
        failure_description="Expected 2026-10-18, Received 2026-10-17",
        allowed_changes=["src/date.ts"],
    )

    archive = tmp_path / "open_test.scopelet"
    CapsulePackager.pack(staging, archive)

    dest_dir = tmp_path / "cli_ws"

    # Test 'scopelet capsule open'
    res_open = runner.invoke(app, ["capsule", "open", str(archive), "--dir", str(dest_dir)])
    assert res_open.exit_code == 0
    assert "Task:     CLI Capsule Open Test" in res_open.output
    assert "Run:      npm test" in res_open.output
    assert "Failure:  Expected 2026-10-18, Received 2026-10-17" in res_open.output
    assert "Editable: src/date.ts" in res_open.output
    assert "[SUCCESS] Capsule extracted to:" in res_open.output

    # Test 'scopelet capsule status' (compliant)
    res_status = runner.invoke(app, ["capsule", "status", "--dir", str(dest_dir)])
    assert res_status.exit_code == 0
    assert "Compliance: PASS" in res_status.output

    # Modify forbidden file and test 'scopelet capsule status' (fails with exit code 1)
    (dest_dir / "test" / "date.test.ts").write_text("modified", encoding="utf-8")
    res_status_fail = runner.invoke(app, ["capsule", "status", "--dir", str(dest_dir)])
    assert res_status_fail.exit_code == 1
    assert "Compliance: FAIL" in res_status_fail.output
    assert "test/date.test.ts (FORBIDDEN)" in res_status_fail.output


def test_cli_capsule_run(tmp_path: Path):
    ws = tmp_path / "run_ws"
    ws.mkdir()
    (ws / "capsule.json").write_text(
        json.dumps({
            "schema_version": "1.0",
            "capsule_hash": "dummy_hash",
            "title": "Run Test",
            "created_at": "2026-10-18T00:00:00Z",
            "command": "npm test",
            "allowed_changes": [],
            "failure_fingerprint": "fp_expected",
            "files": [],
        }),
        encoding="utf-8",
    )

    mock_manifest = CapsuleManifest(
        schema_version="1.0",
        capsule_hash="dummy_hash",
        title="Run Test",
        created_at="2026-10-18T00:00:00Z",
        command="npm test",
        failure_fingerprint="fp_expected",
        files=[],
    )
    mock_res = ExecutionResult(
        command="npm test",
        backend="local_sandbox",
        tree_hash="tree123",
        exit_code=1,
        stdout="FAIL: date mismatch",
        stderr="",
        duration_ms=45,
        fingerprint="fp_expected",
    )

    with patch("scopelet.capsule.runner.CapsuleRunner.run", return_value=(mock_manifest, mock_res)):
        res = runner.invoke(app, ["capsule", "run", "--dir", str(ws)])
        assert res.exit_code == 0
        assert "Run Test" in res.output
        assert "FAIL: date mismatch" in res.output
        assert "Verified standalone reproduction: Failure fingerprint matches exactly." in res.output


def test_cli_capsule_open_errors(tmp_path: Path):
    # Non-existent archive
    non_existent = tmp_path / "missing.scopelet"
    res = runner.invoke(app, ["capsule", "open", str(non_existent)])
    assert res.exit_code == 1
    assert "Capsule file not found" in res.output


def test_status_missing_manifest(tmp_path: Path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    res = runner.invoke(app, ["capsule", "status", "--dir", str(empty_dir)])
    assert res.exit_code == 1
    assert "Missing capsule.json in workspace" in res.output


def test_solver_status_ignores_metadata_and_git(tmp_path: Path):
    ws = tmp_path / "ws_metadata"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "index.ts").write_text("console.log('test');", encoding="utf-8")

    state = CandidateState.from_directory(ws)
    builder = CapsuleBuilder()
    builder.build(
        output_dir=ws,
        state=state,
        title="Ignore metadata test",
        command="npm test",
        failure_fingerprint="fp1",
        allowed_changes=["src/index.ts"],
    )

    # Add solver/metadata files that must be ignored
    (ws / "solution.patch").write_text("diff ...", encoding="utf-8")
    (ws / "solution.json").write_text("{}", encoding="utf-8")
    (ws / ".git").mkdir()
    (ws / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
    (ws / "node_modules").mkdir()
    (ws / "node_modules" / "pkg").mkdir()
    (ws / "node_modules" / "pkg" / "index.js").write_text("module.exports = {};", encoding="utf-8")

    status = CapsuleSolver.get_status(ws)
    assert status.is_compliant is True
    assert status.added_files == []

