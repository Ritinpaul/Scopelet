"""
Unit tests for Scopelet failure capture engine, environment security, and artifact persistence.
"""

import os
from pathlib import Path
import pytest
from scopelet.capture import (
    capture,
    NoFailureDetectedError,
    get_safe_environment,
    get_runtime_info,
    get_lockfile_hash,
    get_git_commit,
    SessionStore,
    ALLOWED_ENV_VARS,
)
from scopelet.models.session import SessionInfo
from scopelet.models.failure import NormalizedFailure

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_environment_allowlist_drops_secrets(monkeypatch):
    """
    Secrets present in the environment must NEVER be captured.
    """
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "AKIAIOSFODNN7EXAMPLE")
    monkeypatch.setenv("STRIPE_API_KEY", "sk_live_fake_SECRET_123")
    monkeypatch.setenv("INTERNAL_PASSWORD", "SuperSecretPass123!")
    monkeypatch.setenv("NODE_ENV", "test")

    safe_env = get_safe_environment()

    # Allowlisted variable should be present
    assert safe_env.get("NODE_ENV") == "test"

    # Secrets must NOT be present
    assert "AWS_SECRET_ACCESS_KEY" not in safe_env
    assert "STRIPE_API_KEY" not in safe_env
    assert "INTERNAL_PASSWORD" not in safe_env

    # Every key in safe_env must be in ALLOWED_ENV_VARS
    for k in safe_env.keys():
        assert k.upper() in ALLOWED_ENV_VARS


def test_runtime_info_captures_node():
    runtime = get_runtime_info()
    assert "node" in runtime
    assert runtime["node"].startswith("v")
    assert "python" in runtime


def test_lockfile_hash_fixture_a():
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    h = get_lockfile_hash(fixture_a)
    assert h is not None
    assert len(h) == 64  # SHA-256


def test_git_commit_captured():
    commit = get_git_commit(ROOT_DIR)
    assert commit is not None
    assert len(commit) >= 7


def test_session_store_persists_all_files(tmp_path):
    store = SessionStore(tmp_path)
    failure = NormalizedFailure(
        schema_version="1.0",
        test="sample test",
        exception="AssertionError",
        message="expected true to be false",
        expected="false",
        actual="true",
        frames=["src/file.ts"],
        fingerprint="abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
    )
    session = SessionInfo(
        schema_version="1.0",
        command="npm test",
        cwd=str(tmp_path),
        exit_code=1,
        duration_ms=450,
        runtime={"node": "v24.8.0"},
        lockfile_hash="hash123",
        git_commit="git123",
        timestamp="2026-10-18T14:00:00Z",
        environment={"NODE_ENV": "test"},
        failure=failure,
    )

    store.save_session(session, stdout="out", stderr="err", failure=failure)

    assert (tmp_path / "stdout.log").read_text(encoding="utf-8") == "out"
    assert (tmp_path / "stderr.log").read_text(encoding="utf-8") == "err"
    assert (tmp_path / "failure.json").exists()
    assert (tmp_path / "session.json").exists()


def test_passing_command_raises_no_failure():
    with pytest.raises(NoFailureDetectedError):
        # A command that exits 0 with no failure
        capture(command="node -e \"process.exit(0)\"", cwd=ROOT_DIR)


def test_capture_fixture_a_timezone_bug(tmp_path):
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    out_dir = tmp_path / ".scopelet"

    result = capture(
        command="npm test -- invoice-timezone",
        cwd=fixture_a,
        output_dir=out_dir,
    )

    assert result.session.exit_code == 1
    assert result.failure.exception == "AssertionError"
    assert result.failure.expected == "2026-10-18"
    assert result.failure.actual == "2026-10-17"
    assert len(result.failure.fingerprint) == 64
    assert (out_dir / "failure.json").exists()
    assert (out_dir / "session.json").exists()


def test_capture_fixture_b_rounding_bug(tmp_path):
    fixture_b = ROOT_DIR / "fixtures" / "rounding-bug"
    out_dir = tmp_path / ".scopelet"

    result = capture(
        command="npm test -- rounding",
        cwd=fixture_b,
        output_dir=out_dir,
    )

    assert result.session.exit_code == 1
    assert result.failure.exception == "AssertionError"
    assert result.failure.expected == "250"
    assert result.failure.actual == "249.99"
    assert len(result.failure.fingerprint) == 64


def test_capture_fixture_c_cache_bug(tmp_path):
    fixture_c = ROOT_DIR / "fixtures" / "cache-bug"
    out_dir = tmp_path / ".scopelet"

    result = capture(
        command="npm test -- cache",
        cwd=fixture_c,
        output_dir=out_dir,
    )

    assert result.session.exit_code == 1
    assert result.failure.exception == "AssertionError"
    assert result.failure.expected == "Alice Smith"
    assert result.failure.actual == "Alice"
    assert len(result.failure.fingerprint) == 64
