"""
Docker container execution engine for strict hermetic isolation.
Mounts workspace read-only with network disabled, non-root user, and restricted CPU/RAM.
"""

import subprocess
import time
from pathlib import Path
from typing import Optional, Dict
from .result import ExecutionResult
from .cache import compute_tree_hash
from .security import DOCKER_SECURITY_CONFIG
from ..fingerprint.normalizer import parse_failure
from ..security.sandbox import truncate_output, validate_mount


class DockerUnavailableError(Exception):
    """Raised when the Docker daemon is unreachable or docker CLI is absent."""
    pass


class DockerRunner:
    """
    Executes commands inside a hardened, isolated Docker container.
    """

    def __init__(
        self,
        image: str = "node:22-alpine",
        default_timeout: int = 120,
    ):
        self.image = image
        self.default_timeout = default_timeout

    @staticmethod
    def is_available() -> bool:
        """
        Checks whether the Docker daemon is reachable and responding.
        """
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return res.returncode == 0
        except Exception:
            return False

    def run(
        self,
        command: str,
        cwd: Path,
        env_override: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Runs the specified command inside a Docker container using DOCKER_SECURITY_CONFIG.
        """
        if not self.is_available():
            raise DockerUnavailableError(
                "Docker daemon is not running or unreachable. Cannot start container isolation."
            )

        actual_timeout = timeout or self.default_timeout
        tree_hash = compute_tree_hash(cwd)
        abs_cwd = str(cwd.resolve())

        # Construct hardened docker run arguments
        # Using normalized forward slashes for Windows compatibility
        mount_path = abs_cwd.replace("\\", "/")
        if not mount_path.startswith("/"):
            # e.g. D:/path -> /d/path for Docker on Windows
            drive = mount_path[0].lower()
            mount_path = f"/{drive}{mount_path[2:]}"

        validate_mount(abs_cwd, "/app", read_only=True)

        cmd_args = [
            "docker", "run", "--rm",
            "--network", DOCKER_SECURITY_CONFIG["network_mode"],
            "--memory", DOCKER_SECURITY_CONFIG["mem_limit"],
            "--cpus", "0.5",
            "--pids-limit", str(DOCKER_SECURITY_CONFIG["pids_limit"]),
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "-v", f"{abs_cwd}:/app:ro",
            "-w", "/app",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs", "/home/node/.npm:rw,noexec,nosuid,size=32m",
            "--tmpfs", "/app/node_modules/.cache:rw,noexec,nosuid,size=64m",
            "-u", "node",
            "-e", "NODE_ENV=test",
            "-e", "CI=true",
        ]

        if env_override:
            for k, v in env_override.items():
                cmd_args.extend(["-e", f"{k}={v}"])

        cmd_args.extend([self.image, "sh", "-c", command])

        start_time = time.perf_counter()
        try:
            proc = subprocess.run(
                cmd_args,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
                encoding="utf-8",
                errors="replace",
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as te:
            stdout = te.stdout or ""
            stderr = f"Container execution timed out after {actual_timeout}s."
            exit_code = 124

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        stdout = truncate_output(stdout)
        stderr = truncate_output(stderr)

        combined = f"{stdout}\n{stderr}"
        failure = parse_failure(combined, cwd=cwd)
        fingerprint = failure.fingerprint if failure else None

        return ExecutionResult(
            schema_version="1.0",
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            backend="docker",
            tree_hash=tree_hash,
            cached=False,
            fingerprint=fingerprint,
            failure=failure,
        )
