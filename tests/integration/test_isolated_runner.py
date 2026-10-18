"""
Integration tests for the Isolated Execution Runner.
Verifies the core Phase 3 invariant:
Host failure fingerprint == Isolated container/runner failure fingerprint.
"""

from pathlib import Path
import pytest
from scopelet.capture import capture
from scopelet.runner import (
    IsolatedRunner,
    LocalIsolatedRunner,
    DockerRunner,
    DockerUnavailableError,
    DOCKER_SECURITY_CONFIG,
)

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_docker_security_policy_compliance():
    """
    Verifies that container security configuration matches all specification requirements.
    """
    assert DOCKER_SECURITY_CONFIG["network_mode"] == "none"
    assert DOCKER_SECURITY_CONFIG["mem_limit"] == "512m"
    assert DOCKER_SECURITY_CONFIG["nano_cpus"] == 500_000_000
    assert DOCKER_SECURITY_CONFIG["read_only"] is True
    assert DOCKER_SECURITY_CONFIG["user"] == "node"
    assert "no-new-privileges" in DOCKER_SECURITY_CONFIG["security_opt"]
    assert "ALL" in DOCKER_SECURITY_CONFIG["cap_drop"]
    assert "/tmp" in DOCKER_SECURITY_CONFIG["tmpfs"]


def test_docker_unavailable_error_when_daemon_offline():
    """
    When Docker daemon is offline or unreachable, DockerRunner.run() must raise DockerUnavailableError.
    """
    if not DockerRunner.is_available():
        runner = DockerRunner()
        with pytest.raises(DockerUnavailableError):
            runner.run("npm test", cwd=ROOT_DIR)


def test_timeout_enforcement():
    """
    Long-running or infinite loop execution must be terminated at timeout limit.
    """
    runner = LocalIsolatedRunner(default_timeout=1)
    # A script that sleeps for 5 seconds must be aborted at 1 second
    res = runner.run("node -e \"setTimeout(()=>{}, 5000)\"", cwd=ROOT_DIR, timeout=1)
    assert res.exit_code == 124
    assert "timed out" in res.stderr.lower()


def test_host_fingerprint_matches_isolated_runner_fixture_a(tmp_path):
    """
    Core Phase 3 verification:
    Host repository failure fingerprint == Isolated execution failure fingerprint.
    """
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    cmd = "npm test -- invoice-timezone"

    # 1. Host capture
    host_capture = capture(command=cmd, cwd=fixture_a, output_dir=tmp_path / "host_a")
    host_fingerprint = host_capture.failure.fingerprint

    # 2. Isolated execution runner
    runner = IsolatedRunner(cache_db_path=tmp_path / "cache.db")
    isolated_result = runner.run(command=cmd, cwd=fixture_a, use_cache=False)
    isolated_fingerprint = isolated_result.fingerprint

    assert host_fingerprint is not None
    assert isolated_fingerprint is not None
    # Crucial assertion: fingerprints MUST match across the isolation boundary!
    assert host_fingerprint == isolated_fingerprint
    assert isolated_result.exit_code == 1
    assert isolated_result.failure is not None
    assert isolated_result.failure.expected == "2026-10-18"
    assert isolated_result.failure.actual == "2026-10-17"


def test_host_fingerprint_matches_isolated_runner_fixture_b(tmp_path):
    """
    Verifies fingerprint parity for Fixture B (rounding bug).
    """
    fixture_b = ROOT_DIR / "fixtures" / "rounding-bug"
    cmd = "npm test -- rounding"

    host_capture = capture(command=cmd, cwd=fixture_b, output_dir=tmp_path / "host_b")
    host_fingerprint = host_capture.failure.fingerprint

    runner = IsolatedRunner(cache_db_path=tmp_path / "cache.db")
    isolated_result = runner.run(command=cmd, cwd=fixture_b, use_cache=False)
    isolated_fingerprint = isolated_result.fingerprint

    assert host_fingerprint == isolated_fingerprint
    assert isolated_result.exit_code == 1
    assert isolated_result.failure is not None
    assert isolated_result.failure.expected == "250"
    assert isolated_result.failure.actual == "249.99"


def test_host_fingerprint_matches_isolated_runner_fixture_c(tmp_path):
    """
    Verifies fingerprint parity for Fixture C (cache bug).
    """
    fixture_c = ROOT_DIR / "fixtures" / "cache-bug"
    cmd = "npm test -- cache"

    host_capture = capture(command=cmd, cwd=fixture_c, output_dir=tmp_path / "host_c")
    host_fingerprint = host_capture.failure.fingerprint

    runner = IsolatedRunner(cache_db_path=tmp_path / "cache.db")
    isolated_result = runner.run(command=cmd, cwd=fixture_c, use_cache=False)
    isolated_fingerprint = isolated_result.fingerprint

    assert host_fingerprint == isolated_fingerprint
    assert isolated_result.exit_code == 1
    assert isolated_result.failure is not None
    assert isolated_result.failure.expected == "Alice Smith"
    assert isolated_result.failure.actual == "Alice"


def test_isolated_runner_serves_from_cache(tmp_path):
    """
    Verifies that running the same command twice serves the second result from cache.
    """
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    cmd = "npm test -- invoice-timezone"
    runner = IsolatedRunner(cache_db_path=tmp_path / "cache.db")

    # 1st run: fresh execution
    r1 = runner.run(command=cmd, cwd=fixture_a, use_cache=True)
    assert r1.cached is False

    # 2nd run: served from SQLite cache
    r2 = runner.run(command=cmd, cwd=fixture_a, use_cache=True)
    assert r2.cached is True
    assert r2.fingerprint == r1.fingerprint
    assert r2.exit_code == r1.exit_code
