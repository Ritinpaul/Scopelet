"""
Unit and integration tests for Phase 11 Privacy Report Generator.
Verifies token extraction, source overlap calculation, metrics aggregation and report formatting.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from scopelet.reports.privacy_report import PrivacyReportData, PrivacyReportGenerator
from scopelet.capsule.packager import CapsulePackager


def test_token_extraction_identifiers_and_strings():
    generator = PrivacyReportGenerator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        f = Path(tmp_dir) / "sample.ts"
        f.write_text(
            "// Comment line ignored\n"
            "const userProject = 'ALPHA_99';\n"
            "function computeTotal(price: number): number {\n"
            "    return price * 1.15;\n"
            "}\n",
            encoding="utf-8",
        )
        identifiers, strings = generator.extract_tokens(f)

        assert "userProject" in identifiers
        assert "computeTotal" in identifiers
        assert "price" in identifiers
        assert "ALPHA_99" in strings


def test_source_overlap_identical_dirs():
    generator = PrivacyReportGenerator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig = Path(tmp_dir) / "orig"
        capsule = Path(tmp_dir) / "capsule"
        orig.mkdir()
        capsule.mkdir()

        code = "export const rate = 42;\nexport const name = 'shared';\n"
        (orig / "test.ts").write_text(code, encoding="utf-8")
        (capsule / "test.ts").write_text(code, encoding="utf-8")

        report = generator.generate_report(original_dir=orig, capsule_target=capsule)
        assert report.original_files == 1
        assert report.capsule_files == 1
        assert report.source_overlap_pct == 100.0


def test_source_overlap_disjoint_dirs():
    generator = PrivacyReportGenerator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig = Path(tmp_dir) / "orig"
        capsule = Path(tmp_dir) / "capsule"
        orig.mkdir()
        capsule.mkdir()

        (orig / "orig.ts").write_text("export const fooVal = 'hello';", encoding="utf-8")
        (capsule / "cap.ts").write_text("export const barNum = 123;", encoding="utf-8")

        report = generator.generate_report(original_dir=orig, capsule_target=capsule)
        assert report.source_overlap_pct == 0.0


def test_source_overlap_partial_formula():
    generator = PrivacyReportGenerator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig = Path(tmp_dir) / "orig"
        capsule = Path(tmp_dir) / "capsule"
        orig.mkdir()
        capsule.mkdir()

        # Original has 4 tokens: id1, id2, str1, str2
        (orig / "orig.ts").write_text(
            "const id1 = 'str1';\nconst id2 = 'str2';\n",
            encoding="utf-8",
        )
        # Capsule retains 2 tokens: id1, str1 + adds new token id3
        (capsule / "cap.ts").write_text(
            "const id1 = 'str1';\nconst id3 = 99;\n",
            encoding="utf-8",
        )

        report = generator.generate_report(original_dir=orig, capsule_target=capsule)
        # 2 retained out of 4 original tokens = 50.0%
        assert report.original_identifiers_retained == 1
        assert report.original_string_literals_retained == 1
        assert report.source_overlap_pct == 50.0


def test_loc_and_file_counting():
    generator = PrivacyReportGenerator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig = Path(tmp_dir) / "orig"
        capsule = Path(tmp_dir) / "capsule"
        orig.mkdir()
        capsule.mkdir()

        (orig / "a.ts").write_text("line 1\nline 2\nline 3\n", encoding="utf-8")
        (orig / "b.ts").write_text("line 1\nline 2\n", encoding="utf-8")
        (capsule / "reduced.ts").write_text("line 1\n", encoding="utf-8")

        report = generator.generate_report(original_dir=orig, capsule_target=capsule)
        assert report.original_files == 2
        assert report.capsule_files == 1
        assert report.original_loc == 5
        assert report.capsule_loc == 1


def test_scanner_metrics_aggregation():
    generator = PrivacyReportGenerator(canaries={"CANARY_SECRET_123"})
    with tempfile.TemporaryDirectory() as tmp_dir:
        orig = Path(tmp_dir) / "orig"
        capsule = Path(tmp_dir) / "capsule"
        orig.mkdir()
        capsule.mkdir()

        (orig / "orig.ts").write_text("export const x = 1;", encoding="utf-8")

        # Capsule contains leaks: 1 AWS key, 1 Canary, 1 internal IP, 1 proprietary project
        (capsule / "leak.ts").write_text(
            'const aws = "AKIA1234567890ABCDEF";\n'
            'const canary = "CANARY_SECRET_123";\n'
            'const ip = "10.0.1.25";\n'
            'const project = "CUSTOMER_PROJECT_NEBULA";\n',
            encoding="utf-8",
        )

        report = generator.generate_report(original_dir=orig, capsule_target=capsule)
        assert report.known_secret_patterns >= 1
        assert report.configured_canaries >= 1
        assert report.internal_urls >= 1
        assert report.potential_proprietary_terms >= 1


def test_privacy_report_text_formatting():
    data = PrivacyReportData(
        original_files=684,
        capsule_files=7,
        original_loc=176204,
        capsule_loc=511,
        known_secret_patterns=0,
        configured_canaries=0,
        email_addresses=0,
        internal_urls=0,
        original_identifiers_retained=21,
        original_string_literals_retained=14,
        potential_proprietary_terms=2,
        source_overlap_pct=11.8,
    )

    rendered = data.format_text()
    assert "Scopelet Privacy Report" in rendered
    assert "Original files                    684" in rendered
    assert "Capsule files                       7" in rendered
    assert "Original LOC                  176,204" in rendered
    assert "Capsule LOC                       511" in rendered
    assert "Known secret patterns               0" in rendered
    assert "Configured canaries                 0" in rendered
    assert "Email addresses                     0" in rendered
    assert "Internal URLs                       0" in rendered
    assert "Original identifiers retained      21" in rendered
    assert "Original string literals retained  14" in rendered
    assert "Potential proprietary terms         2" in rendered
    assert "Source overlap                  11.8%" in rendered
    assert "Manual review: REQUIRED" in rendered
    assert "Scopelet minimizes disclosure." in rendered
    assert "It does not mathematically guarantee confidentiality." in rendered


def test_report_generation_from_scopelet_archive():
    generator = PrivacyReportGenerator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        orig = root / "orig"
        cap_dir = root / "capsule_stage"
        orig.mkdir()
        cap_dir.mkdir()

        (orig / "app.ts").write_text("export const x = 1;\nexport const y = 2;", encoding="utf-8")
        (cap_dir / "app.ts").write_text("export const x = 1;", encoding="utf-8")

        archive_file = root / "test_artifact.scopelet"
        CapsulePackager.pack(cap_dir, archive_file)

        report = generator.generate_report(original_dir=orig, capsule_target=archive_file)
        assert report.original_files == 1
        assert report.capsule_files == 1
        assert report.original_loc == 2
        assert report.capsule_loc == 1
        assert report.source_overlap_pct > 0.0
