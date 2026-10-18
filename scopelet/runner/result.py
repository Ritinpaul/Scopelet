"""
Execution result models for isolated runner executions.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field
from ..models.failure import NormalizedFailure


class ExecutionResult(BaseModel):
    """
    Standardized execution outcome produced by the isolated execution runner.
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    command: str = Field(..., description="Executed command string")
    exit_code: int = Field(..., description="Process exit code")
    stdout: str = Field(..., description="Captured standard output")
    stderr: str = Field(..., description="Captured standard error")
    duration_ms: int = Field(..., description="Wall-clock execution duration in milliseconds")
    backend: Literal["docker", "local_sandbox"] = Field(..., description="Isolation backend used")
    tree_hash: str = Field(..., description="SHA-256 tree hash of the executed workspace state")
    cached: bool = Field(default=False, description="Whether this result was served from cache")
    fingerprint: Optional[str] = Field(default=None, description="Normalized failure fingerprint hash if failed")
    failure: Optional[NormalizedFailure] = Field(default=None, description="Normalized failure object if failed")
