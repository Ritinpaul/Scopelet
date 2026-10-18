"""
Privacy review gate verifying manual checklist authorizations before export.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..scanner.orchestrator import PrivacyScanner
from .models import ApprovalChecklist, ApprovalRecord


class PrivacyApprovalError(Exception):
    """Raised when manual privacy review conditions or approvals fail."""
    pass


class PrivacyReviewGate:
    """
    Coordinates human verification checks and records approval tokens.
    """

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir.resolve()
        self.approval_file = self.workspace_dir / ".scopelet" / "approval.json"
        self.scanner = PrivacyScanner()

    def check_preconditions(self) -> Tuple[bool, Optional[str]]:
        """
        Runs privacy and secret scanner to ensure no critical leaks exist prior to review.
        """
        report = self.scanner.scan(self.workspace_dir)
        if report.has_critical_leaks:
            return False, "Critical secrets or privacy leaks detected in workspace. Export blocked."
        return True, None

    def conduct_review(
        self,
        approver: str,
        checklist: ApprovalChecklist,
        capsule_hash: Optional[str] = None,
    ) -> ApprovalRecord:
        """
        Conducts the manual privacy review and saves the cryptographically signed approval record.
        """
        if not approver or not approver.strip():
            raise PrivacyApprovalError("Approver name or identity must be provided.")

        precond_ok, precond_err = self.check_preconditions()
        if not precond_ok:
            raise PrivacyApprovalError(f"Review rejected: {precond_err}")

        if not checklist.is_fully_confirmed():
            raise PrivacyApprovalError("Review rejected: all checklist items must be explicitly confirmed.")

        record = ApprovalRecord(
            approved=True,
            approved_by=approver.strip(),
            checklist=checklist,
            capsule_hash=capsule_hash,
        )
        record.signature = record.compute_signature()

        self.approval_file.parent.mkdir(parents=True, exist_ok=True)
        self.approval_file.write_text(
            json.dumps(record.model_dump(), indent=2),
            encoding="utf-8",
        )
        return record

    def is_approved(self) -> Tuple[bool, Optional[ApprovalRecord], Optional[str]]:
        """
        Checks whether the workspace has a valid and intact manual approval record.
        """
        if not self.approval_file.exists():
            return False, None, "No approval record found. Run 'scopelet review' first."

        try:
            data = json.loads(self.approval_file.read_text(encoding="utf-8"))
            record = ApprovalRecord.model_validate(data)
        except Exception as e:
            return False, None, f"Corrupted approval record: {e}"

        if not record.approved or not record.checklist.is_fully_confirmed():
            return False, record, "Approval checklist is incomplete or unapproved."

        expected_sig = record.compute_signature()
        if record.signature != expected_sig:
            return False, record, "Approval signature mismatch: record may have been tampered with."

        return True, record, None
