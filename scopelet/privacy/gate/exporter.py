"""
Capsule export engine enforcing privacy approval and safe packaging.
Injects approval records into capsule.json and excludes private mappings from exported archives.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set

from ...capsule.packager import CapsulePackager
from ...capsule.builder import CapsuleBuilder
from ...capsule.models import CapsuleFile, CapsuleManifest
from ...capsule.hasher import compute_capsule_hash
from ..scanner.orchestrator import PrivacyScanner
from ..sanitizer.mapping import MappingStore
from .reviewer import PrivacyReviewGate, PrivacyApprovalError
from .models import ApprovalRecord

EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
    ".vitest",
}


class CapsuleExporter:
    """
    Manages final capsule packaging with mandatory human approval verification.
    """

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = workspace_dir.resolve()
        self.gate = PrivacyReviewGate(self.workspace_dir)
        self.scanner = PrivacyScanner()

    def export(
        self,
        output_file: Path,
        require_approval: bool = True,
    ) -> Path:
        """
        Exports a reproduction capsule into a .scopelet archive after verifying manual review approval.
        """
        approval_record: Optional[ApprovalRecord] = None

        if require_approval:
            approved, record, reason = self.gate.is_approved()
            if not approved or not record:
                raise PrivacyApprovalError(
                    f"Export blocked: Manual privacy review has not been completed ({reason}). "
                    "Run 'scopelet review' first."
                )
            approval_record = record

        # Pre-export privacy scan
        scan_report = self.scanner.scan(self.workspace_dir)
        if scan_report.has_critical_leaks:
            raise PrivacyApprovalError(
                "Export blocked: Critical secrets or privacy leaks detected in workspace."
            )

        output_path = output_file.resolve()
        staging_dir = Path(tempfile.mkdtemp(prefix="scopelet_export_stage_"))

        try:
            # Copy all safe files into staging directory
            for item in sorted(self.workspace_dir.rglob("*")):
                if not item.is_file():
                    continue

                rel_parts = item.relative_to(self.workspace_dir).parts
                if any(part in EXCLUDE_DIRS for part in rel_parts):
                    continue

                rel_posix = item.relative_to(self.workspace_dir).as_posix()
                # Strictly exclude private mappings and unbundled approvals
                if not MappingStore.is_safe_capsule_path(rel_posix):
                    continue
                if rel_posix.startswith(".scopelet/"):
                    continue
                if item.name.startswith(".env"):
                    continue

                dest = staging_dir / rel_posix
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)

            # Inject approval record into capsule.json
            capsule_json_path = staging_dir / "capsule.json"
            if capsule_json_path.exists():
                manifest_data = json.loads(capsule_json_path.read_text(encoding="utf-8"))
                if approval_record:
                    manifest_data["approval"] = approval_record.model_dump()
                capsule_json_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
            else:
                # If capsule.json doesn't exist, create minimal manifest
                now_utc = "2026-10-18T00:00:00Z"
                minimal_manifest = CapsuleManifest(
                    schema_version="1.0",
                    title="Exported reproduction capsule",
                    created_at=now_utc,
                    runtime={"node": "22"},
                    command="npm test",
                    approval=approval_record.model_dump() if approval_record else None,
                )
                capsule_json_path.write_text(
                    json.dumps(minimal_manifest.model_dump(), indent=2),
                    encoding="utf-8",
                )

            # Pack staging directory into .scopelet archive
            CapsulePackager.pack(staging_dir, output_path)

            # Post-packaging verification scan
            post_scan = self.scanner.scan(output_path)
            if post_scan.has_critical_leaks:
                if output_path.exists():
                    output_path.unlink()
                raise PrivacyApprovalError("Post-export scan detected privacy leaks in final capsule package.")

            return output_path
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
