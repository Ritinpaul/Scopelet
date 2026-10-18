"""
Data models for the Manual Privacy Approval Gate.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Dict, Optional
from pydantic import BaseModel, Field

DEFAULT_GATE_SCHEMA_VERSION = "1.0"


class ApprovalChecklist(BaseModel):
    """
    Five-item human privacy review checklist.
    """
    retained_identifiers_reviewed: bool = False
    fixtures_reviewed: bool = False
    configuration_reviewed: bool = False
    environment_values_absent: bool = False
    export_approved: bool = False

    def is_fully_confirmed(self) -> bool:
        """Returns True if every required review item has been explicitly confirmed."""
        return (
            self.retained_identifiers_reviewed
            and self.fixtures_reviewed
            and self.configuration_reviewed
            and self.environment_values_absent
            and self.export_approved
        )


class ApprovalRecord(BaseModel):
    """
    Cryptographically verifiable approval record authorizing capsule export.
    """
    schema_version: str = DEFAULT_GATE_SCHEMA_VERSION
    approved: bool = False
    approved_by: str = ""
    approved_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    checklist: ApprovalChecklist = Field(default_factory=ApprovalChecklist)
    capsule_hash: Optional[str] = None
    signature: Optional[str] = None

    def compute_signature(self, secret_seed: str = "scopelet_gate") -> str:
        """Computes a SHA-256 signature for this approval payload."""
        payload = {
            "approved": self.approved,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "checklist": self.checklist.model_dump(),
            "capsule_hash": self.capsule_hash or "",
            "seed": secret_seed,
        }
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
