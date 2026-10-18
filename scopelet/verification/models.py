"""
Data models for patch ingestion and private repository verification reports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class TestRunVerdict(BaseModel):
    """
    Standardized test run verdict within the verification engine.
    """
    __test__ = False

    command: str = Field(..., description="Executed command string")
    passed: bool = Field(..., description="Whether the test run passed successfully")
    exit_code: int = Field(..., description="Process exit code")
    duration_ms: int = Field(default=0, description="Execution duration in milliseconds")
    fingerprint: Optional[str] = Field(default=None, description="Normalized failure fingerprint if test failed")
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")


class VerificationReport(BaseModel):
    """
    Structured outcome of patch verification against private codebase.
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    verdict: Literal["ACCEPTED", "REJECTED"] = Field(..., description="Overall acceptance verdict")
    patch_hash: str = Field(..., description="SHA-256 hash of applied solution.patch")
    modified_files: List[str] = Field(default_factory=list, description="List of files modified by patch")
    target_test: TestRunVerdict = Field(..., description="Target bug verification test result")
    regression_test: Optional[TestRunVerdict] = Field(default=None, description="Regression test suite result if executed")
    compliance_passed: bool = Field(..., description="Whether all patch modifications adhere to allowed_changes")
    rejection_reasons: List[str] = Field(default_factory=list, description="List of reasons for rejection if not accepted")
    created_at: str = Field(..., description="UTC ISO timestamp of verification run")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional additional metadata")
