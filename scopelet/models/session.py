"""
Pydantic data models for capture sessions and environment metadata.
"""

from typing import Optional, Dict
from pydantic import BaseModel, Field
from .failure import NormalizedFailure


class SessionInfo(BaseModel):
    """
    Metadata recording the execution parameters, runtime versions,
    lockfile state, and allowlisted environment.
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    command: str = Field(..., description="The command executed")
    cwd: str = Field(..., description="Working directory path")
    exit_code: int = Field(..., description="Process exit code")
    duration_ms: int = Field(..., description="Execution duration in milliseconds")
    runtime: Dict[str, str] = Field(
        default_factory=dict,
        description="Captured runtime versions (e.g. node, npm, python)"
    )
    lockfile_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of project lockfile"
    )
    git_commit: Optional[str] = Field(
        default=None,
        description="Current Git commit SHA at capture time"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp in UTC")
    environment: Dict[str, str] = Field(
        default_factory=dict,
        description="Allowlisted environment variables (secrets strictly excluded)"
    )
    failure: Optional[NormalizedFailure] = Field(
        default=None,
        description="Captured normalized failure and fingerprint"
    )
