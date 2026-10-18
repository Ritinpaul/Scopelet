"""
Oracle evaluator for candidate reduction states.
Verifies whether a reduced candidate state reproduces the exact target failure fingerprint.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from ..runner import IsolatedRunner
from .candidate import CandidateState
from .cache import ReducerCache


class OracleVerdict(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    ERROR = "ERROR"


class OracleResult(BaseModel):
    verdict: OracleVerdict
    fingerprint: Optional[str] = None
    exit_code: int = 0
    duration_ms: int = 0
    cached: bool = False
    error_message: Optional[str] = None
    stdout: str = ""
    stderr: str = ""


class ReducerOracle:
    """
    Evaluates candidate repository states using IsolatedRunner against an expected fingerprint.
    """

    def __init__(
        self,
        command: str,
        expected_fingerprint: str,
        workspace_dir: Path,
        runner: Optional[IsolatedRunner] = None,
        cache: Optional[ReducerCache] = None,
        timeout: int = 60,
    ):
        self.command = command
        self.expected_fingerprint = expected_fingerprint
        self.workspace_dir = workspace_dir.resolve()
        self.runner = runner or IsolatedRunner(prefer_docker=False)
        self.cache = cache
        self.timeout = timeout
        self.total_evaluations = 0

    def evaluate(self, candidate: CandidateState) -> OracleResult:
        """
        Tests whether candidate state reproduces the expected failure fingerprint.
        """
        tree_hash = candidate.compute_tree_hash()

        # Check cache
        if self.cache:
            cached_data = self.cache.get(tree_hash=tree_hash, command=self.command)
            if cached_data:
                return OracleResult(
                    verdict=OracleVerdict(cached_data["verdict"]),
                    fingerprint=cached_data.get("fingerprint"),
                    exit_code=cached_data.get("exit_code", 0),
                    duration_ms=cached_data.get("duration_ms", 0),
                    cached=True,
                    error_message=cached_data.get("error_message"),
                )

        self.total_evaluations += 1

        # Materialize candidate into isolated workspace
        candidate.materialize(self.workspace_dir, link_node_modules=True)

        # Execute test command in workspace
        result = self.runner.run(
            command=self.command,
            cwd=self.workspace_dir,
            timeout=self.timeout,
            use_cache=False,
        )

        # Determine verdict
        if result.exit_code == 0:
            # Test passed: failure was lost
            verdict = OracleVerdict.MISMATCH
            error_msg = "Command succeeded without failure (exit code 0)"
        elif result.fingerprint and result.fingerprint == self.expected_fingerprint:
            # Exact failure fingerprint preserved
            verdict = OracleVerdict.MATCH
            error_msg = None
        elif result.fingerprint and result.fingerprint != self.expected_fingerprint:
            # Different failure occurred
            verdict = OracleVerdict.MISMATCH
            error_msg = f"Fingerprint mismatch: expected {self.expected_fingerprint[:12]}..., got {result.fingerprint[:12]}..."
        else:
            # Execution error or non-normalized failure
            verdict = OracleVerdict.ERROR
            error_msg = result.error_message or f"Process terminated with exit code {result.exit_code}"

        oracle_result = OracleResult(
            verdict=verdict,
            fingerprint=result.fingerprint,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            cached=False,
            error_message=error_msg,
            stdout=result.stdout,
            stderr=result.stderr,
        )

        # Store in cache
        if self.cache:
            self.cache.put(
                tree_hash=tree_hash,
                command=self.command,
                verdict=verdict.value,
                fingerprint=result.fingerprint,
                exit_code=result.exit_code,
                duration_ms=result.duration_ms,
                error_message=error_msg,
            )

        return oracle_result
