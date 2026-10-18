"""
Pydantic data models for Scopelet capsule archives, manifests and task specifications.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CapsuleFile(BaseModel):
    """
    Metadata record for a file bundled inside a capsule.
    """
    path: str = Field(..., description="Normalized relative POSIX path of the file")
    hash: str = Field(..., description="SHA-256 content hash of the file")
    size_bytes: int = Field(default=0, description="Size of the file in bytes")


class CapsuleManifest(BaseModel):
    """
    Manifest metadata for an independent Scopelet reproduction capsule.
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    capsule_hash: str = Field(default="", description="Deterministic SHA-256 hash of the entire capsule")
    title: str = Field(..., description="Human-readable title describing the defect")
    created_at: str = Field(..., description="UTC ISO timestamp of capsule creation")
    runtime: Dict[str, str] = Field(default_factory=lambda: {"node": "22"}, description="Runtime engine specifications")
    command: str = Field(default="npm test", description="Verification test command")
    allowed_changes: List[str] = Field(default_factory=list, description="List of files permitted to be modified in a fix")
    expected: Dict[str, Any] = Field(default_factory=lambda: {"test_should_pass": True}, description="Expected outcome when bug is fixed")
    network_allowed: bool = Field(default=False, description="Whether network access is permitted during verification")
    failure_fingerprint: str = Field(default="", description="Target oracle failure fingerprint of the unpatched bug")
    failure_description: Optional[str] = Field(default=None, description="Human-readable summary of failure symptoms")
    files: List[CapsuleFile] = Field(default_factory=list, description="List of regular files included in the capsule")
    approval: Optional[Dict[str, Any]] = Field(default=None, description="Manual privacy review approval record")


class TaskSpec(BaseModel):
    """
    task.yaml specification defining the verification contract for solvers.
    """
    title: str = Field(..., description="Defect title")
    command: str = Field(..., description="Verification test command")
    failure_description: Optional[str] = Field(default=None, description="Expected failure symptom")
    allowed_changes: List[str] = Field(default_factory=list, description="Files permitted for bugfix modification")
    expected: Dict[str, Any] = Field(default_factory=lambda: {"test_should_pass": True}, description="Expected verification conditions")
    runtime: Dict[str, str] = Field(default_factory=lambda: {"node": "22"}, description="Target runtime specifications")
    network: Dict[str, bool] = Field(default_factory=lambda: {"allowed": False}, description="Network isolation rules")


class SolutionVerification(BaseModel):
    """
    Verification execution outcome for a candidate solution.
    """
    command: str = Field(..., description="Verification command executed")
    exit_code: int = Field(..., description="Exit code of verification process")
    success: bool = Field(..., description="Whether verification passed completely")
    duration_ms: int = Field(default=0, description="Execution duration in milliseconds")
    fingerprint: Optional[str] = Field(default=None, description="Failure fingerprint if failed")


class SolutionMetadata(BaseModel):
    """
    Metadata specification for a submitted capsule solution (solution.json).
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    capsule_hash: str = Field(..., description="SHA-256 hash of the capsule manifest being solved")
    patch_hash: str = Field(..., description="SHA-256 hash of the unified diff solution.patch")
    modified_files: List[str] = Field(default_factory=list, description="Files modified in the patch")
    created_at: str = Field(..., description="UTC ISO timestamp of solution submission")
    author: str = Field(default="external_solver", description="Author or solver identity")
    verification: Optional[SolutionVerification] = Field(default=None, description="Pre-submission verification outcome")
    summary: Optional[str] = Field(default=None, description="Optional description of the fix")
