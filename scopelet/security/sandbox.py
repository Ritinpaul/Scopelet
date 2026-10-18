"""
Security sandbox enforcement, resource limits and safe archive extraction.
Provides container security configurations, process limits and traversal protections.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SecurityViolationError(Exception):
    """Raised when an operation violates security boundaries or sandboxing rules."""
    pass


# Strict Docker container security configuration
DOCKER_SECURITY_CONFIG: Dict[str, Any] = {
    "network_mode": "none",
    "mem_limit": "512m",
    "nano_cpus": 500_000_000,  # 0.5 CPUs
    "pids_limit": 256,
    "read_only": True,
    "tmpfs": {
        "/tmp": "rw,noexec,nosuid,size=64m",
        "/home/node/.npm": "rw,noexec,nosuid,size=32m",
        "/app/node_modules/.cache": "rw,noexec,nosuid,size=64m",
    },
    "user": "node",
    "security_opt": ["no-new-privileges"],
    "cap_drop": ["ALL"],
}

# Local process isolation policy
LOCAL_PROCESS_POLICY: Dict[str, Any] = {
    "default_timeout_seconds": 60,
    "max_timeout_seconds": 300,
    "max_output_bytes": 10 * 1024 * 1024,  # 10 MB limit to prevent memory exhaustion
}

MAX_OUTPUT_BYTES = 10 * 1024 * 1024  # 10 MB


def truncate_output(text: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """
    Truncates output text if it exceeds the maximum byte limit.
    Appends a truncation marker to alert the caller.
    """
    if not text:
        return ""
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated + "\n...[OUTPUT TRUNCATED: Exceeded 10MB limit]"


def validate_mount(host_path: str, container_path: str, read_only: bool = True) -> None:
    """
    Validates a proposed volume mount for security violations.
    Disallows mounting the Docker socket or sensitive host paths.
    """
    normalized_host = host_path.replace("\\", "/").lower()
    normalized_container = container_path.replace("\\", "/").lower()

    # Block Docker socket mounting
    if "docker.sock" in normalized_host or "docker.sock" in normalized_container:
        raise SecurityViolationError(
            "Mounting the Docker socket is strictly prohibited to prevent host escape."
        )

    # Block sensitive system directories on host
    forbidden_host_prefixes = (
        "/etc",
        "/proc",
        "/sys",
        "/dev",
        "/root",
        "/var/run",
        "c:/windows",
        "c:/program files",
    )
    for prefix in forbidden_host_prefixes:
        if normalized_host == prefix or normalized_host.startswith(prefix + "/"):
            raise SecurityViolationError(
                f"Mounting sensitive host directory '{host_path}' is prohibited."
            )


def validate_docker_args(args: List[str]) -> None:
    """
    Validates a list of Docker run command arguments against security requirements.
    Ensures network isolation, dropped capabilities, no-new-privileges and pids limits.
    """
    args_str = " ".join(args)

    if "--privileged" in args:
        raise SecurityViolationError("Docker --privileged flag is strictly prohibited.")

    # Check for docker socket
    for arg in args:
        if "docker.sock" in arg:
            raise SecurityViolationError("Docker socket mount detected in container arguments.")

    # Verify network isolation
    has_network_none = False
    for i, arg in enumerate(args):
        if arg == "--network" and i + 1 < len(args) and args[i + 1] == "none":
            has_network_none = True
        elif arg.startswith("--network=none"):
            has_network_none = True
    if not has_network_none:
        raise SecurityViolationError("Container must be configured with --network none.")

    # Verify no-new-privileges
    has_no_new_privs = any(
        arg == "no-new-privileges" or "--security-opt=no-new-privileges" in arg or "--security-opt no-new-privileges" in args_str
        for arg in args
    )
    if not has_no_new_privs:
        raise SecurityViolationError("Container must enforce no-new-privileges.")

    # Verify cap-drop ALL
    has_cap_drop = any(
        arg == "ALL" or "--cap-drop=ALL" in arg or "--cap-drop ALL" in args_str
        for arg in args
    )
    if not has_cap_drop:
        raise SecurityViolationError("Container must drop all capabilities (--cap-drop ALL).")

    # Verify non-root user
    for i, arg in enumerate(args):
        if arg in ("-u", "--user"):
            if i + 1 < len(args) and args[i + 1] in ("root", "0", "0:0"):
                raise SecurityViolationError("Running container as root is strictly prohibited.")
        elif arg.startswith("--user="):
            val = arg.split("=", 1)[1]
            if val in ("root", "0", "0:0"):
                raise SecurityViolationError("Running container as root is strictly prohibited.")


class SafeExtractor:
    """
    Safe archive extractor with protections against Zip Slip, zip bombs and escaping symlinks.
    """

    def __init__(
        self,
        max_total_bytes: int = 500 * 1024 * 1024,  # 500 MB
        max_file_count: int = 10_000,
        max_single_file_bytes: int = 50 * 1024 * 1024,  # 50 MB
    ):
        self.max_total_bytes = max_total_bytes
        self.max_file_count = max_file_count
        self.max_single_file_bytes = max_single_file_bytes

    def validate_entry_path(self, entry_name: str, target_dir: Path) -> Path:
        """
        Validates that an archive entry name does not attempt directory traversal.
        Returns the resolved safe destination path.
        """
        target_resolved = target_dir.resolve()

        # Reject absolute paths or Windows drive letters
        if os.path.isabs(entry_name) or ":" in entry_name or entry_name.startswith("/"):
            raise SecurityViolationError(
                f"Absolute path or drive letter detected in archive entry: {entry_name}"
            )

        # Normalize and reject parent traversal
        parts = Path(entry_name).parts
        if ".." in parts:
            raise SecurityViolationError(
                f"Directory traversal component '..' detected in archive entry: {entry_name}"
            )

        dest_path = (target_resolved / entry_name).resolve()
        if not dest_path.is_relative_to(target_resolved):
            raise SecurityViolationError(
                f"Resolved path escapes target directory: {entry_name} -> {dest_path}"
            )

        return dest_path

    def validate_symlink(self, link_path: Path, target_dir: Path) -> None:
        """
        Ensures a symlink does not resolve outside the target directory.
        """
        if not link_path.is_symlink():
            return
        target_resolved = target_dir.resolve()
        resolved_link = link_path.resolve()
        if not resolved_link.is_relative_to(target_resolved):
            raise SecurityViolationError(
                f"Symlink {link_path} targets outside destination: {resolved_link}"
            )

    def extract_zip(self, archive_path: Path, destination_dir: Path) -> Path:
        """
        Safely extracts all entries from a zip archive into destination_dir.
        Enforces path safety, size limits and symlink containment.
        """
        archive = archive_path.resolve()
        destination = destination_dir.resolve()
        destination.mkdir(parents=True, exist_ok=True)

        if not archive.exists():
            raise FileNotFoundError(f"Archive not found: {archive}")

        total_bytes = 0
        file_count = 0

        with zipfile.ZipFile(archive, "r") as zf:
            members = zf.infolist()
            if len(members) > self.max_file_count:
                raise SecurityViolationError(
                    f"Archive exceeds maximum file count ({len(members)} > {self.max_file_count})."
                )

            for member in members:
                file_count += 1
                if member.file_size > self.max_single_file_bytes:
                    raise SecurityViolationError(
                        f"Entry {member.filename} exceeds max file size "
                        f"({member.file_size} > {self.max_single_file_bytes})."
                    )

                total_bytes += member.file_size
                if total_bytes > self.max_total_bytes:
                    raise SecurityViolationError(
                        f"Archive exceeds total uncompressed size limit "
                        f"({total_bytes} > {self.max_total_bytes})."
                    )

                dest_path = self.validate_entry_path(member.filename, destination)

                if member.is_dir():
                    dest_path.mkdir(parents=True, exist_ok=True)
                else:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, dest_path.open("wb") as dst:
                        dst.write(src.read())

        return destination
