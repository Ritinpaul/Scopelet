"""
Adversarial security tests for container isolation, archive extraction and resource constraints.
Validates 15+ security requirements defined in Phase 21.
"""

import io
import os
import zipfile
from pathlib import Path
import pytest

from scopelet.security.sandbox import (
    DOCKER_SECURITY_CONFIG,
    LOCAL_PROCESS_POLICY,
    MAX_OUTPUT_BYTES,
    SafeExtractor,
    SecurityViolationError,
    truncate_output,
    validate_docker_args,
    validate_mount,
)


def test_docker_security_config_network_none():
    """Security parameter check: Network isolation must be strictly set to 'none'."""
    assert DOCKER_SECURITY_CONFIG["network_mode"] == "none"


def test_docker_security_config_memory_limit():
    """Security parameter check: RAM limit must be capped at 512m."""
    assert DOCKER_SECURITY_CONFIG["mem_limit"] == "512m"


def test_docker_security_config_cpu_limit():
    """Security parameter check: CPU limit must be capped at 0.5 cores (500,000,000 nano CPUs)."""
    assert DOCKER_SECURITY_CONFIG["nano_cpus"] == 500_000_000


def test_docker_security_config_pids_limit():
    """Security parameter check: Process count must be restricted to 256 to stop fork bombs."""
    assert DOCKER_SECURITY_CONFIG["pids_limit"] == 256


def test_docker_security_config_read_only_root():
    """Security parameter check: Container root filesystem must be mounted read-only."""
    assert DOCKER_SECURITY_CONFIG["read_only"] is True


def test_docker_security_config_user_non_root():
    """Security parameter check: Container execution must run as non-root user 'node'."""
    assert DOCKER_SECURITY_CONFIG["user"] == "node"


def test_docker_security_config_security_opt():
    """Security parameter check: no-new-privileges must be configured."""
    assert "no-new-privileges" in DOCKER_SECURITY_CONFIG["security_opt"]


def test_docker_security_config_cap_drop_all():
    """Security parameter check: All Linux capabilities must be dropped."""
    assert DOCKER_SECURITY_CONFIG["cap_drop"] == ["ALL"]


def test_docker_security_config_tmpfs_mounts():
    """Security parameter check: Writable storage must be restricted to tmpfs."""
    tmpfs = DOCKER_SECURITY_CONFIG["tmpfs"]
    assert "/tmp" in tmpfs
    assert "/home/node/.npm" in tmpfs
    assert "/app/node_modules/.cache" in tmpfs


def test_docker_args_reject_privileged():
    """Validates that privileged container mode is rejected."""
    args = ["docker", "run", "--privileged", "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges"]
    with pytest.raises(SecurityViolationError, match="privileged"):
        validate_docker_args(args)


def test_docker_args_reject_docker_socket():
    """Validates that mounting the Docker socket in container args is rejected."""
    args = [
        "docker", "run",
        "-v", "/var/run/docker.sock:/var/run/docker.sock",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
    ]
    with pytest.raises(SecurityViolationError, match="Docker socket"):
        validate_docker_args(args)


def test_docker_args_reject_missing_network_none():
    """Validates that running without --network none is rejected."""
    args = [
        "docker", "run",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "alpine", "sh",
    ]
    with pytest.raises(SecurityViolationError, match="network none"):
        validate_docker_args(args)


def test_docker_args_reject_root_user():
    """Validates that running as root user is rejected."""
    args = [
        "docker", "run",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "-u", "root",
        "alpine", "sh",
    ]
    with pytest.raises(SecurityViolationError, match="root"):
        validate_docker_args(args)


def test_mount_validation_blocks_docker_socket():
    """Validates that host mount paths containing docker.sock are blocked."""
    with pytest.raises(SecurityViolationError, match="Docker socket"):
        validate_mount("/var/run/docker.sock", "/app/docker.sock")


def test_mount_validation_blocks_sensitive_host_dirs():
    """Validates that mounting sensitive system directories is blocked."""
    for sensitive_path in ["/etc", "/proc", "/sys", "/dev", "/root"]:
        with pytest.raises(SecurityViolationError, match="sensitive host directory"):
            validate_mount(sensitive_path, "/app/mnt")


def test_safe_extractor_rejects_parent_traversal(tmp_path):
    """Validates that SafeExtractor rejects path traversal entries with '..'."""
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        zf.writestr("../../evil.sh", "echo pwned")
    zip_bytes.seek(0)

    zip_file = tmp_path / "traversal.zip"
    zip_file.write_bytes(zip_bytes.getvalue())

    dest_dir = tmp_path / "extracted"
    extractor = SafeExtractor()
    with pytest.raises(SecurityViolationError, match="Directory traversal"):
        extractor.extract_zip(zip_file, dest_dir)


def test_safe_extractor_rejects_absolute_path(tmp_path):
    """Validates that SafeExtractor rejects entries with absolute paths."""
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        zf.writestr("/etc/passwd", "root:x:0:0")
    zip_bytes.seek(0)

    zip_file = tmp_path / "absolute.zip"
    zip_file.write_bytes(zip_bytes.getvalue())

    dest_dir = tmp_path / "extracted"
    extractor = SafeExtractor()
    with pytest.raises(SecurityViolationError, match="Absolute path"):
        extractor.extract_zip(zip_file, dest_dir)


def test_safe_extractor_rejects_zip_bomb_file_count(tmp_path):
    """Validates that SafeExtractor rejects archives exceeding max file count."""
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        for i in range(15):
            zf.writestr(f"file_{i}.txt", "test")
    zip_bytes.seek(0)

    zip_file = tmp_path / "many_files.zip"
    zip_file.write_bytes(zip_bytes.getvalue())

    dest_dir = tmp_path / "extracted"
    extractor = SafeExtractor(max_file_count=10)
    with pytest.raises(SecurityViolationError, match="maximum file count"):
        extractor.extract_zip(zip_file, dest_dir)


def test_safe_extractor_rejects_zip_bomb_file_size(tmp_path):
    """Validates that SafeExtractor rejects single entries exceeding max file size."""
    zip_bytes = io.BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as zf:
        zf.writestr("big_file.bin", "A" * 2048)
    zip_bytes.seek(0)

    zip_file = tmp_path / "big_file.zip"
    zip_file.write_bytes(zip_bytes.getvalue())

    dest_dir = tmp_path / "extracted"
    extractor = SafeExtractor(max_single_file_bytes=1024)
    with pytest.raises(SecurityViolationError, match="max file size"):
        extractor.extract_zip(zip_file, dest_dir)


def test_safe_extractor_validates_escaping_symlink(tmp_path):
    """Validates that SafeExtractor detects escaping symlinks outside destination."""
    dest_dir = tmp_path / "sandbox"
    dest_dir.mkdir()
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret_data")

    escaping_link = dest_dir / "link_to_secret"
    try:
        os.symlink(outside_file, escaping_link)
        extractor = SafeExtractor()
        with pytest.raises(SecurityViolationError, match="Symlink.*targets outside"):
            extractor.validate_symlink(escaping_link, dest_dir)
    except OSError:
        pytest.skip("Symlink creation not permitted in this OS environment")


def test_output_truncation_enforces_10mb_limit():
    """Validates that output streams exceeding 10MB are truncated with an alert marker."""
    eleven_mb = "X" * (11 * 1024 * 1024)
    truncated = truncate_output(eleven_mb, max_bytes=MAX_OUTPUT_BYTES)
    assert len(truncated.encode("utf-8")) <= MAX_OUTPUT_BYTES + 200
    assert "[OUTPUT TRUNCATED: Exceeded 10MB limit]" in truncated


def test_output_truncation_passes_normal_text():
    """Validates that standard size output passes without truncation."""
    normal_text = "All 42 tests passed successfully."
    assert truncate_output(normal_text) == normal_text
