"""
Dynamic execution tracer for Node.js and TypeScript test suites.
Instruments executions with V8 coverage collection to extract real runtime footprints.
"""

from pathlib import Path
import os
import subprocess
import tempfile
import time
from typing import Optional, Dict
from pydantic import BaseModel, Field

from .trace_parser import parse_v8_coverage_dir, DynamicTraceResult


class TraceExecutionReport(BaseModel):
    command: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    trace: DynamicTraceResult = Field(default_factory=DynamicTraceResult)


class DynamicTracer:
    """
    Executes commands with V8 coverage collection enabled to record
    which repository files and functions are invoked at runtime.
    """

    def __init__(self, default_timeout: int = 120):
        self.default_timeout = default_timeout

    def trace(
        self,
        command: str,
        cwd: Path,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> TraceExecutionReport:
        """
        Runs a test command with NODE_V8_COVERAGE enabled and returns the execution report
        along with parsed dynamic trace coverage.
        """
        target_cwd = Path(cwd).resolve()
        exec_timeout = timeout or self.default_timeout

        with tempfile.TemporaryDirectory(prefix="scopelet_v8_") as tmp_dir:
            coverage_dir = Path(tmp_dir)

            # Build environment with coverage path
            run_env = os.environ.copy()
            if env:
                run_env.update(env)
            run_env["NODE_V8_COVERAGE"] = str(coverage_dir)

            start_time = time.perf_counter()
            proc = subprocess.run(
                command,
                cwd=str(target_cwd),
                env=run_env,
                shell=True,
                capture_output=True,
                text=True,
                timeout=exec_timeout,
                encoding="utf-8",
                errors="replace",
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Parse coverage results
            trace_result = parse_v8_coverage_dir(coverage_dir, target_cwd)

            return TraceExecutionReport(
                command=command,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
                stdout=proc.stdout,
                stderr=proc.stderr,
                trace=trace_result,
            )
