"""
Pydantic schemas for the Scopelet FastAPI REST endpoints (Phase 28).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Payload to create a new minimization and verification session."""
    repo_dir: str = Field(..., description="Absolute or relative path to the target repository")
    title: Optional[str] = Field(None, description="Descriptive title of the defect or session")


class SessionResponse(BaseModel):
    """Details of an active Scopelet session."""
    session_id: str
    repo_dir: str
    title: str
    status: str
    created_at: str
    fingerprint: Optional[str] = None
    files_count: Optional[int] = None
    reduced_files_count: Optional[int] = None
    capsule_hash: Optional[str] = None


class CaptureRequest(BaseModel):
    """Payload to capture a failing test."""
    command: str = Field(..., description="Test command that fails on the defect")
    timeout: int = Field(300, description="Execution timeout in seconds")


class CaptureResponse(BaseModel):
    """Result of failure capture."""
    session_id: str
    fingerprint: str
    test_name: str
    exception: str
    exit_code: int
    duration_ms: int
    stack_frames: List[str]


class AnalyzeResponse(BaseModel):
    """Result of static dependency and dynamic trace analysis."""
    session_id: str
    total_nodes: int
    slice_files: List[str]
    dynamic_coverage_count: int


class ReduceRequest(BaseModel):
    """Parameters for delta-debugging reduction."""
    max_evaluations: int = Field(50, description="Maximum evaluations permitted")
    enable_ai_ranker: bool = Field(True, description="Enable AI relevance ranking prioritization")


class ReduceResponse(BaseModel):
    """Result of repository minimization."""
    session_id: str
    initial_files: int
    final_files: int
    evaluations: int
    cache_hits: int
    kept_files: List[str]
    reduction_percentage: float


class SanitizeResponse(BaseModel):
    """Result of behavior-preserving AST sanitization."""
    session_id: str
    sanitized: bool
    replacements_count: int
    fingerprint_preserved: bool


class ExportRequest(BaseModel):
    """Payload to export a reproduction capsule."""
    output_path: Optional[str] = Field(None, description="Optional target .scopelet archive filepath")
    auto_approve: bool = Field(True, description="Automatically approve privacy review checklist")


class ExportResponse(BaseModel):
    """Result of capsule export."""
    session_id: str
    archive_path: str
    capsule_hash: str
    file_size_bytes: int


class VerifyRequest(BaseModel):
    """Payload to verify a candidate fix patch against private repository."""
    solution_patch: str = Field(..., description="Unified diff patch content")
    target_cmd: Optional[str] = Field(None, description="Target bug test command override")
    hidden_regression_cmd: Optional[str] = Field(None, description="Hidden private regression test command")
    full_suite_cmd: Optional[str] = Field(None, description="Full repository test suite command")


class VerifyResponse(BaseModel):
    """Authoritative verdict from Private Hidden Verifier."""
    session_id: str
    verdict: str
    patch_hash: str
    target_test_passed: bool
    hidden_regression_passed: bool
    rejection_reasons: List[str]
    duration_ms: int


class ReportResponse(BaseModel):
    """Privacy and minimization metrics report."""
    session_id: str
    title: str
    original_files: int
    original_loc: int
    capsule_files: int
    capsule_loc: int
    reduction_pct: float
    secret_findings_count: int
    canaries_found: int
    manual_review_status: str
