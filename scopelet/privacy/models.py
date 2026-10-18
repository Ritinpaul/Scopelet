"""
Data models and sensitivity enumerations for privacy and secret scanning.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Sensitivity(str, Enum):
    """
    Semantic sensitivity classifications for identifiers and content.
    """
    SAFE = "safe"
    POTENTIALLY_PROPRIETARY = "potentially_proprietary"
    PERSONAL_INFORMATION = "personal_information"
    BUSINESS_SENSITIVE = "business_sensitive"
    UNKNOWN = "unknown"


class SecretFinding(BaseModel):
    """
    Detected secret or sensitive token occurrence.
    """
    file_path: str = Field(..., description="Relative path of file containing the finding")
    line_number: int = Field(..., description="Line number of occurrence (1-indexed)")
    category: str = Field(..., description="Category: api_key, jwt, private_key, entropy, email, ip, canary, git_leak, semantic")
    description: str = Field(..., description="Human-readable description of detected secret")
    matched_text: str = Field(..., description="Masked or truncated snippet")
    entropy: Optional[float] = Field(default=None, description="Calculated Shannon entropy if applicable")
    severity: str = Field(default="HIGH", description="Severity level: CRITICAL, HIGH, MEDIUM, LOW")


class ScanReport(BaseModel):
    """
    Consolidated scan results for a capsule or workspace.
    """
    target_path: str = Field(..., description="Path to scanned directory or archive")
    total_files_scanned: int = Field(default=0, description="Total files evaluated")
    findings: List[SecretFinding] = Field(default_factory=list, description="All secret and privacy findings")
    has_critical_leaks: bool = Field(default=False, description="Whether any CRITICAL or HIGH severity findings were detected")
    scanned_at: str = Field(..., description="UTC ISO timestamp of scan")
