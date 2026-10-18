"""
Unit and integration tests for Phase 12 Manual Privacy Approval Gate.
Verifies review checklist preconditions, cryptographic signatures, approval requirements and safe capsule export.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from scopelet.privacy.gate.models import ApprovalChecklist, ApprovalRecord
from scopelet.privacy.gate.reviewer import PrivacyReviewGate, PrivacyApprovalError
from scopelet.privacy.gate.exporter import CapsuleExporter


def test_gate_precondition_blocks_review_if_critical_secrets_exist():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "index.ts").write_text('const secretKey = "AKIA1234567890ABCDEF";', encoding="utf-8")

        gate = PrivacyReviewGate(root)
        precond_ok, precond_err = gate.check_preconditions()
        assert precond_ok is False
        assert "Critical secrets or privacy leaks detected" in precond_err

        checklist = ApprovalChecklist(
            retained_identifiers_reviewed=True,
            fixtures_reviewed=True,
            configuration_reviewed=True,
            environment_values_absent=True,
            export_approved=True,
        )
        with pytest.raises(PrivacyApprovalError) as exc_info:
            gate.conduct_review(approver="SecurityLead", checklist=checklist)
        assert "Review rejected" in str(exc_info.value)


def test_gate_conduct_review_all_confirmed_saves_signed_record():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "index.ts").write_text("export const answer = 42;", encoding="utf-8")

        gate = PrivacyReviewGate(root)
        checklist = ApprovalChecklist(
            retained_identifiers_reviewed=True,
            fixtures_reviewed=True,
            configuration_reviewed=True,
            environment_values_absent=True,
            export_approved=True,
        )

        record = gate.conduct_review(
            approver="Ritinpaul",
            checklist=checklist,
            capsule_hash="capsule_hash_123",
        )

        assert record.approved is True
        assert record.approved_by == "Ritinpaul"
        assert record.signature is not None
        assert gate.approval_file.exists()

        # Check is_approved verification
        is_ok, loaded_record, err = gate.is_approved()
        assert is_ok is True
        assert err is None
        assert loaded_record.approved_by == "Ritinpaul"


def test_gate_conduct_review_rejects_if_any_item_unconfirmed():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "index.ts").write_text("export const answer = 42;", encoding="utf-8")

        gate = PrivacyReviewGate(root)
        # Checklist with export_approved = False
        incomplete_checklist = ApprovalChecklist(
            retained_identifiers_reviewed=True,
            fixtures_reviewed=True,
            configuration_reviewed=True,
            environment_values_absent=True,
            export_approved=False,
        )

        with pytest.raises(PrivacyApprovalError) as exc_info:
            gate.conduct_review(approver="Lead", checklist=incomplete_checklist)
        assert "all checklist items must be explicitly confirmed" in str(exc_info.value)
        assert not gate.approval_file.exists()


def test_gate_is_approved_detects_tampered_or_missing_record():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        gate = PrivacyReviewGate(root)

        # Missing approval
        is_ok, record, err = gate.is_approved()
        assert is_ok is False
        assert "No approval record found" in err

        # Create valid record then tamper with it
        (root / "index.ts").write_text("export const x = 1;", encoding="utf-8")
        checklist = ApprovalChecklist(
            retained_identifiers_reviewed=True,
            fixtures_reviewed=True,
            configuration_reviewed=True,
            environment_values_absent=True,
            export_approved=True,
        )
        gate.conduct_review(approver="Dev1", checklist=checklist)

        # Tamper with approval record
        content = json.loads(gate.approval_file.read_text(encoding="utf-8"))
        content["approved_by"] = "ImposterUser"
        gate.approval_file.write_text(json.dumps(content), encoding="utf-8")

        is_ok, record, err = gate.is_approved()
        assert is_ok is False
        assert "signature mismatch" in err


def test_exporter_blocks_export_when_not_approved():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "index.ts").write_text("export const x = 1;", encoding="utf-8")
        out_file = root / "unapproved.scopelet"

        exporter = CapsuleExporter(root)
        with pytest.raises(PrivacyApprovalError) as exc_info:
            exporter.export(out_file, require_approval=True)
        assert "Export blocked" in str(exc_info.value)
        assert not out_file.exists()


def test_exporter_succeeds_when_approved_and_injects_approval():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src = root / "src"
        src.mkdir()
        (src / "calc.ts").write_text("export function sum(a: number, b: number) { return a + b; }", encoding="utf-8")

        # Existing capsule.json
        manifest_data = {
            "schema_version": "1.0",
            "title": "Invoice calculation bug",
            "created_at": "2026-10-18T10:00:00Z",
            "command": "npm test",
            "runtime": {"node": "22"},
            "allowed_changes": ["src/calc.ts"],
        }
        (root / "capsule.json").write_text(json.dumps(manifest_data), encoding="utf-8")

        # Create private mapping that must NEVER be exported
        priv_dir = root / ".scopelet" / "private"
        priv_dir.mkdir(parents=True)
        (priv_dir / "mapping.json").write_text('{"PROJECT_SECRET": "customer_A"}', encoding="utf-8")

        # Conduct review
        gate = PrivacyReviewGate(root)
        checklist = ApprovalChecklist(
            retained_identifiers_reviewed=True,
            fixtures_reviewed=True,
            configuration_reviewed=True,
            environment_values_absent=True,
            export_approved=True,
        )
        gate.conduct_review(approver="Auditor", checklist=checklist)

        # Export capsule
        out_archive = root / "approved_capsule.scopelet"
        exporter = CapsuleExporter(root)
        exported_path = exporter.export(out_archive, require_approval=True)

        assert exported_path.exists()
        assert exported_path == out_archive

        # Inspect contents of the exported zip archive
        with zipfile.ZipFile(out_archive, "r") as zf:
            namelist = zf.namelist()
            assert "src/calc.ts" in namelist
            assert "capsule.json" in namelist

            # Strictly verify private mapping is excluded
            assert not any(".scopelet" in name for name in namelist)
            assert not any("private" in name for name in namelist)
            assert not any("mapping.json" in name for name in namelist)

            # Verify approval was injected into capsule.json
            with zf.open("capsule.json") as f:
                capsule_data = json.loads(f.read().decode("utf-8"))
                assert "approval" in capsule_data
                assert capsule_data["approval"]["approved"] is True
                assert capsule_data["approval"]["approved_by"] == "Auditor"
                assert capsule_data["approval"]["signature"] is not None


def test_exporter_allows_bypass_with_no_approval_flag():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "index.ts").write_text("export const val = 100;", encoding="utf-8")
        out_file = root / "test_bypass.scopelet"

        exporter = CapsuleExporter(root)
        exported = exporter.export(out_file, require_approval=False)

        assert exported.exists()
        assert exported == out_file
