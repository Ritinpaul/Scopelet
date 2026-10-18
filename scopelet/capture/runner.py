"""
Command execution and failure capture orchestrator.
Executes test commands, captures streams, normalizes failures, and generates deterministic fingerprints.
"""

import datetime
import subprocess
import time
from pathlib import Path
from typing import Optional, NamedTuple
from ..fingerprint.normalizer import parse_failure
from ..models.failure import NormalizedFailure
from ..models.session import SessionInfo
from .environment import (
    get_runtime_info,
    get_lockfile_hash,
    get_git_commit,
    get_safe_environment,
)
from .session import SessionStore


class NoFailureDetectedError(Exception):
    """Raised when the executed test command succeeds without any failure."""
    pass


class CaptureResult(NamedTuple):
    session: SessionInfo
    failure: NormalizedFailure
    stdout: str
    stderr: str
    output_dir: Path


def capture(
    command: str,
    cwd: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    timeout: Optional[int] = 300,
) -> CaptureResult:
    """
    Executes a test command, captures its stdout and stderr, extracts a canonical
    normalized failure fingerprint and saves session artifacts.
    """
    target_cwd = (cwd or Path.cwd()).resolve()
    target_output_dir = output_dir or (target_cwd / ".scopelet")

    # Capture start timestamp in UTC ISO format
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    start_time = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=str(target_cwd),
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    duration_ms = int((time.perf_counter() - start_time) * 1000)

    combined_output = f"{proc.stdout}\n{proc.stderr}"

    # Parse failure from stdout/stderr
    failure = parse_failure(combined_output, cwd=target_cwd)

    if proc.returncode == 0 and failure is None:
        raise NoFailureDetectedError(
            f"Command '{command}' succeeded with exit code 0. No failure detected."
        )

    if failure is None:
        # Fallback generic failure if command failed with non-zero exit code
        from ..fingerprint.hasher import compute_fingerprint
        failure = NormalizedFailure(
            schema_version="1.0",
            test="CommandExecution",
            exception="ProcessExitError",
            message=f"Process exited with non-zero code {proc.returncode}",
            expected=None,
            actual=str(proc.returncode),
            frames=[],
        )
        failure.fingerprint = compute_fingerprint(failure.canonical_dict())

    # Build session metadata
    session_info = SessionInfo(
        schema_version="1.0",
        command=command,
        cwd=str(target_cwd),
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        runtime=get_runtime_info(),
        lockfile_hash=get_lockfile_hash(target_cwd),
        git_commit=get_git_commit(target_cwd),
        timestamp=timestamp,
        environment=get_safe_environment(),
        failure=failure,
    )

    # Persist artifacts to output directory
    store = SessionStore(target_output_dir)
    store.save_session(
        session_info=session_info,
        stdout=proc.stdout,
        stderr=proc.stderr,
        failure=failure,
    )

    return CaptureResult(
        session=session_info,
        failure=failure,
        stdout=proc.stdout,
        stderr=proc.stderr,
        output_dir=target_output_dir,
    )
