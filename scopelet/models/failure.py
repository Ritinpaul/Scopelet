"""
Pydantic data models for normalized failure representations and fingerprints.
"""

from typing import Optional
from pydantic import BaseModel, Field


class NormalizedFailure(BaseModel):
    """
    Normalized representation of a test or execution failure.
    Line numbers, timings, memory addresses, and non-deterministic IDs are stripped.
    """
    schema_version: str = Field(default="1.0", description="Schema version")
    test: str = Field(..., description="Normalized test name or suite name")
    exception: str = Field(..., description="Exception or error type name (e.g. AssertionError)")
    message: str = Field(..., description="Normalized error message with volatile values stripped")
    expected: Optional[str] = Field(default=None, description="Expected value from assertion")
    actual: Optional[str] = Field(default=None, description="Actual received value from assertion")
    frames: list[str] = Field(
        default_factory=list,
        description="List of normalized relative file paths involved in the failure stack"
    )
    fingerprint: str = Field(
        default="",
        description="SHA-256 fingerprint hash of the canonical failure representation"
    )

    def canonical_dict(self) -> dict[str, object]:
        """
        Returns a dictionary containing only the invariant fields that define the defect.
        """
        return {
            "test": self.test,
            "exception": self.exception,
            "expected": self.expected,
            "actual": self.actual,
            "frames": sorted(list(set(self.frames))),
        }
