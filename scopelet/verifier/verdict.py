"""
Verdict classifications and data models for the Private Hidden Verifier.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from ..verification.models import TestRunVerdict


class Verdict(str, Enum):
    """
    Final decision verdict rendered by the Private Hidden Verifier oracle.
    """
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REVIEW = "REVIEW"


class PolicyResult(BaseModel):
    """
    Result of evaluating an individual patch boundary or security policy.
    """
    policy_name: str = Field(..., description="Name of the security/boundary policy")
    passed: bool = Field(..., description="Whether the patch complies with this policy")
    details: str = Field(..., description="Evaluation notes or violation details")
    severity: Literal["CRITICAL", "WARNING"] = Field(
        default="CRITICAL",
        description="Severity level if violation occurs",
    )


class HiddenVerifierReport(BaseModel):
    """
    Authoritative verification report produced by the Private Hidden Verifier.
    """
    __test__ = False

    schema_version: str = Field(default="1.0", description="Schema version")
    verdict: Verdict = Field(..., description="Authoritative verdict: ACCEPT, REJECT, or REVIEW")
    patch_hash: str = Field(..., description="SHA-256 hash of the applied patch")
    un_sanitized: bool = Field(default=False, description="Whether patch identifiers were un-sanitized")
    modified_files: List[str] = Field(default_factory=list, description="Files modified by patch")
    target_test: Optional[TestRunVerdict] = Field(default=None, description="Original failing bug reproduction test result")
    hidden_regression_test: Optional[TestRunVerdict] = Field(default=None, description="Hidden regression test suite result")
    full_test_suite: Optional[TestRunVerdict] = Field(default=None, description="Complete repository test suite result")
    type_check: Optional[TestRunVerdict] = Field(default=None, description="Type checker result (e.g. tsc or mypy)")
    build_check: Optional[TestRunVerdict] = Field(default=None, description="Build pipeline validation result")
    lint_check: Optional[TestRunVerdict] = Field(default=None, description="Linter analysis result")
    policy_results: List[PolicyResult] = Field(default_factory=list, description="Boundary and security policy checks")
    unexpected_files: List[str] = Field(default_factory=list, description="Unexpected files modified or created")
    rejection_reasons: List[str] = Field(default_factory=list, description="List of reasons if rejected")
    review_notes: List[str] = Field(default_factory=list, description="Diagnostic notes if review is required")
    duration_ms: int = Field(default=0, description="Total verification duration in milliseconds")
    created_at: str = Field(..., description="ISO UTC timestamp of verification run")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional extra metadata")
