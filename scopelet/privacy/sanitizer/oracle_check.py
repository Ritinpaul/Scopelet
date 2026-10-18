"""
Failure reproducibility oracle verification after AST sanitizer transformations.
Verifies whether a transformed workspace reproduces the exact target failure fingerprint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from ...runner import IsolatedRunner


class OracleCheckResult(BaseModel):
    """Result of failure oracle verification."""
    is_valid: bool
    exit_code: int = 0
    actual_fingerprint: Optional[str] = None
    message: str = ""


class OracleCheck:
    """
    Executes test commands on the workspace to verify defect preservation.
    """

    def __init__(
        self,
        command: str,
        expected_fingerprint: str,
        runner: Optional[IsolatedRunner] = None,
        timeout: int = 60,
    ):
        self.command = command
        self.expected_fingerprint = expected_fingerprint
        self.runner = runner or IsolatedRunner(prefer_docker=False)
        self.timeout = timeout

    def verify(self, workspace_dir: Path) -> OracleCheckResult:
        """
        Runs the test command and checks if the failure fingerprint matches expected_fingerprint.
        """
        target = workspace_dir.resolve()
        result = self.runner.run(
            command=self.command,
            cwd=target,
            timeout=self.timeout,
            use_cache=False,
        )

        if result.exit_code == 0:
            return OracleCheckResult(
                is_valid=False,
                exit_code=0,
                actual_fingerprint=None,
                message="Command succeeded without failure (exit code 0)",
            )

        if result.fingerprint and result.fingerprint == self.expected_fingerprint:
            return OracleCheckResult(
                is_valid=True,
                exit_code=result.exit_code,
                actual_fingerprint=result.fingerprint,
                message=f"Deterministic failure fingerprint preserved ({result.fingerprint[:12]}...)",
            )

        mismatch_fp = result.fingerprint or "no_fingerprint"
        return OracleCheckResult(
            is_valid=False,
            exit_code=result.exit_code,
            actual_fingerprint=result.fingerprint,
            message=(
                f"Fingerprint mismatch: expected {self.expected_fingerprint[:12]}..., "
                f"got {mismatch_fp[:12]}..."
            ),
        )
