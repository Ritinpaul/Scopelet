"""
Hermetic local process runner with restricted environment and resource limits.
Used for deterministic test execution and fallback when container virtualization is unavailable.
"""

import subprocess
import time
from pathlib import Path
from typing import Optional, Dict
from .result import ExecutionResult
from .cache import compute_tree_hash
from .security import LOCAL_PROCESS_POLICY
from ..capture.environment import get_safe_environment
from ..fingerprint.normalizer import parse_failure


class LocalIsolatedRunner:
    """
    Executes commands with stripped environment variables and resource constraints.
    """

    def __init__(self, default_timeout: int = 60):
        self.default_timeout = default_timeout

    def run(
        self,
        command: str,
        cwd: Path,
        env_override: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """
        Executes command with restricted environment and strict timeout.
        """
        actual_timeout = timeout or self.default_timeout

        # 1. Cleaned, allowlisted environment
        safe_env = get_safe_environment()
        # Enforce offline / blocked proxy to mitigate network egress
        safe_env["HTTP_PROXY"] = "http://127.0.0.1:0"
        safe_env["HTTPS_PROXY"] = "http://127.0.0.1:0"
        safe_env["ALL_PROXY"] = "socks5://127.0.0.1:0"
        safe_env["NO_PROXY"] = ""

        if env_override:
            safe_env.update(env_override)

        # 2. Compute tree hash before execution
        tree_hash = compute_tree_hash(cwd)

        # 3. Execute with timer
        start_time = time.perf_counter()
        try:
            proc = subprocess.run(
                command,
                cwd=str(cwd),
                shell=True,
                capture_output=True,
                text=True,
                timeout=actual_timeout,
                env=safe_env,
                encoding="utf-8",
                errors="replace",
            )
            stdout = proc.stdout
            stderr = proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as te:
            stdout = te.stdout or ""
            stderr = f"Execution timed out after {actual_timeout} seconds."
            exit_code = 124

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        # Enforce output length limit
        max_bytes = LOCAL_PROCESS_POLICY["max_output_bytes"]
        if len(stdout) > max_bytes:
            stdout = stdout[:max_bytes] + "\n...[OUTPUT TRUNCATED]"
        if len(stderr) > max_bytes:
            stderr = stderr[:max_bytes] + "\n...[OUTPUT TRUNCATED]"

        # 4. Extract failure fingerprint
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
            backend="local_sandbox",
            tree_hash=tree_hash,
            cached=False,
            fingerprint=fingerprint,
            failure=failure,
        )
