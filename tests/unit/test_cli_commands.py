"""
Unit tests for polished Scopelet CLI command surface (Phase 27).
Tests all core subcommands, init, capsule workflows and review/export gates.
"""

from pathlib import Path
import pytest
from typer.testing import CliRunner

from apps.cli.main import app
from scopelet.capsule.builder import CapsuleBuilder
from scopelet.reducer.candidate import CandidateState

runner = CliRunner()


def test_cli_help():
    """Validates that the top-level CLI help lists all required core commands."""
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    help_text = res.stdout

    expected_commands = [
        "init",
        "capture",
        "analyze",
        "reduce",
        "sanitize",
        "review",
        "export",
        "submit",
        "verify",
        "create",
        "capsule",
    ]
    for cmd in expected_commands:
        assert cmd in help_text, f"Command '{cmd}' must be present in CLI help"


def test_cli_capsule_help():
    """Validates that the capsule subgroup lists open, run, status, submit and verify."""
    res = runner.invoke(app, ["capsule", "--help"])
    assert res.exit_code == 0
    help_text = res.stdout

    expected_subcommands = ["open", "run", "status", "submit", "verify"]
    for sub in expected_subcommands:
        assert sub in help_text, f"Capsule subcommand '{sub}' must be present"


def test_cli_init_command(tmp_path):
    """Validates that scopelet init creates .scopelet/config.yaml."""
    res = runner.invoke(app, ["init", "--cwd", str(tmp_path)])
    assert res.exit_code == 0
    config_file = tmp_path / ".scopelet" / "config.yaml"
    assert config_file.exists()
    content = config_file.read_text(encoding="utf-8")
    assert "schema_version: '1.0'" in content
    assert "strict_canary_audit: true" in content


def test_cli_init_command_idempotent(tmp_path):
    """Validates that running scopelet init multiple times is idempotent."""
    res1 = runner.invoke(app, ["init", "--cwd", str(tmp_path)])
    assert res1.exit_code == 0
    res2 = runner.invoke(app, ["init", "--cwd", str(tmp_path)])
    assert res2.exit_code == 0
    assert "already initialized" in res2.stdout


def test_cli_capsule_status_command(tmp_path):
    """Validates that scopelet capsule status checks file compliance against capsule.json."""
    ws = tmp_path / "capsule_ws"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "src" / "index.ts").write_text("console.log('hi');", encoding="utf-8")
    (ws / "package.json").write_text('{"name": "test"}', encoding="utf-8")

    state = CandidateState(root_dir=ws, active_files={"src/index.ts", "package.json"})
    builder = CapsuleBuilder()
    builder.build(
        output_dir=ws,
        state=state,
        title="Status CLI Test",
        command="npm test",
        failure_fingerprint="fp_status",
    )

    res = runner.invoke(app, ["capsule", "status", "--dir", str(ws)])
    assert res.exit_code == 0
    assert "Compliance: PASS" in res.stdout


def test_cli_review_and_export_flow(tmp_path):
    """Validates manual review approval gate followed by export via CLI commands."""
    ws = tmp_path / "export_ws"
    ws.mkdir()
    (ws / "index.ts").write_text("export const val = 1;", encoding="utf-8")
    (ws / "package.json").write_text('{"name": "exp"}', encoding="utf-8")

    state = CandidateState(root_dir=ws, active_files={"index.ts", "package.json"})
    builder = CapsuleBuilder()
    builder.build(
        output_dir=ws,
        state=state,
        title="Export CLI Test",
        command="npm test",
        failure_fingerprint="fp_export",
    )

    # 1. Review approval with --yes
    res_rev = runner.invoke(app, ["review", str(ws), "--approver", "SecurityAuditor", "--yes"])
    assert res_rev.exit_code == 0
    assert "Export Authorization Approved" in res_rev.stdout

    # 2. Export capsule to .scopelet archive
    archive_out = tmp_path / "exported.scopelet"
    res_exp = runner.invoke(app, ["export", str(ws), "--output", str(archive_out)])
    assert res_exp.exit_code == 0
    assert archive_out.exists()
    assert "Capsule successfully exported" in res_exp.stdout
