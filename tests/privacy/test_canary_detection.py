"""
Tests for canary token detection, git leak scanner and semantic sensitivity classification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scopelet.privacy.models import Sensitivity
from scopelet.privacy.scanner.canary_scanner import CanaryScanner
from scopelet.privacy.scanner.git_scanner import GitScanner
from scopelet.privacy.scanner.semantic_scanner import SemanticScanner
from scopelet.privacy.scanner.orchestrator import PrivacyScanner
from scopelet.capsule.packager import CapsulePackager


def test_canary_scanner_exact_match():
    scanner = CanaryScanner(canaries={"CANARY_SECRET_ALPHA_999"})
    text = "const canary = 'CANARY_SECRET_ALPHA_999';\nconst safe = 'hello';"
    findings = scanner.scan_text(text, "index.ts")

    assert len(findings) == 1
    assert findings[0].category == "canary"
    assert findings[0].line_number == 1
    assert findings[0].severity == "CRITICAL"


def test_canary_scanner_dynamic_add_canary():
    scanner = CanaryScanner()
    scanner.add_canary("MY_PRIVATE_CANARY_VALUE")

    text = "console.log('Test token:', 'MY_PRIVATE_CANARY_VALUE');"
    findings = scanner.scan_text(text, "src/main.ts")

    assert len(findings) == 1
    assert findings[0].category == "canary"
    assert findings[0].line_number == 1


def test_canary_scanner_pattern_match():
    scanner = CanaryScanner()
    text = """
    const token = 'CANARY_RANDOM_SEED_XYZ123';
    const conf = 'CONFIDENTIAL_INTERNAL_KEY_44';
    const prop = 'PROPRIETARY_ALGO_TOKEN';
    """
    findings = scanner.scan_text(text, "test.ts")

    assert len(findings) == 3
    assert all(f.category == "canary" for f in findings)
    assert all(f.severity == "CRITICAL" for f in findings)


def test_git_scanner_detects_git_folder():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        git_dir = root / ".git" / "objects"
        git_dir.mkdir(parents=True)
        (git_dir / "pack-1234.pack").write_bytes(b"dummy git pack content")

        scanner = GitScanner()
        findings = scanner.scan_directory(root)

        assert len(findings) >= 1
        assert any(f.category == "git_leak" and ".git" in f.file_path for f in findings)
        assert any(f.severity == "CRITICAL" for f in findings)


def test_git_scanner_detects_gitmodules_and_gitconfig():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / ".gitmodules").write_text('[submodule "foo"]\npath = bar\nurl = git@github.com:foo/bar.git')
        (root / ".gitconfig").write_text("[user]\nname = Test\nemail = test@internal.corp")

        scanner = GitScanner()
        findings = scanner.scan_directory(root)

        assert len(findings) == 2
        categories = {f.matched_text for f in findings}
        assert ".gitmodules" in categories
        assert ".gitconfig" in categories


def test_git_scanner_clean_directory_has_no_findings():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        (root / "src").mkdir()
        (root / "src" / "index.ts").write_text("export const foo = 1;")

        scanner = GitScanner()
        findings = scanner.scan_directory(root)

        assert len(findings) == 0


def test_semantic_classifier_identifies_proprietary():
    scanner = SemanticScanner()
    assert scanner.classify_identifier("CUSTOMER_PROJECT_NEBULA_7429") == Sensitivity.POTENTIALLY_PROPRIETARY
    assert scanner.classify_identifier("PROJECT_ALPHA_CORE") == Sensitivity.POTENTIALLY_PROPRIETARY
    assert scanner.classify_identifier("CONFIDENTIAL_REPORT_GEN") == Sensitivity.POTENTIALLY_PROPRIETARY
    assert scanner.classify_identifier("GOLDMAN_PRICING_FEED") == Sensitivity.POTENTIALLY_PROPRIETARY


def test_semantic_classifier_identifies_pii():
    scanner = SemanticScanner()
    assert scanner.classify_identifier("user_social_security") == Sensitivity.PERSONAL_INFORMATION
    assert scanner.classify_identifier("credit_card_num") == Sensitivity.PERSONAL_INFORMATION
    assert scanner.classify_identifier("patient_record") == Sensitivity.PERSONAL_INFORMATION


def test_semantic_classifier_identifies_business_sensitive():
    scanner = SemanticScanner()
    assert scanner.classify_identifier("pricing_model") == Sensitivity.BUSINESS_SENSITIVE
    assert scanner.classify_identifier("margin_rate") == Sensitivity.BUSINESS_SENSITIVE
    assert scanner.classify_identifier("hedge_strategy") == Sensitivity.BUSINESS_SENSITIVE


def test_semantic_classifier_identifies_safe_and_unknown():
    scanner = SemanticScanner()
    assert scanner.classify_identifier("id") == Sensitivity.SAFE
    assert scanner.classify_identifier("calculate") == Sensitivity.SAFE
    assert scanner.classify_identifier("unknown_helper_var") == Sensitivity.UNKNOWN


def test_semantic_scanner_text_scan():
    scanner = SemanticScanner()
    text = """
    function computeMargin(pricing_model, margin_rate) {
        const ssn = '000-00-0000';
        const project = 'CUSTOMER_PROJECT_ORION_99';
        return 42;
    }
    """
    findings = scanner.scan_text(text, "pricing.ts")

    assert len(findings) >= 4
    categories = {f.category for f in findings}
    assert "semantic_proprietary" in categories
    assert "semantic_pii" in categories
    assert "semantic_business" in categories


def test_privacy_orchestrator_directory_scan():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src = root / "src"
        src.mkdir()

        # Clean file
        (src / "clean.ts").write_text("export function add(a: number, b: number): number { return a + b; }")

        # Secret file
        (src / "secret.ts").write_text('const aws = "AKIA1234567890ABCDEF";\nconst key = "CANARY_TOKEN_99";')

        orchestrator = PrivacyScanner(canaries={"CANARY_TOKEN_99"})
        report = orchestrator.scan(root)

        assert report.total_files_scanned == 2
        assert report.has_critical_leaks is True
        assert len(report.findings) >= 2


def test_privacy_orchestrator_scopelet_archive_scan():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        payload = root / "payload"
        payload.mkdir()

        stripe_key = "sk_" + "live_" + "fake_SECRET_98765432101234567890"
        (payload / "app.ts").write_text(f'const stripe = "{stripe_key}";')
        (payload / "config.json").write_text('{"token": "CANARY_ARCHIVE_123"}')

        archive_path = root / "test_capsule.scopelet"
        CapsulePackager.pack(payload, archive_path)

        orchestrator = PrivacyScanner()
        report = orchestrator.scan(archive_path)

        assert report.total_files_scanned == 2
        assert report.has_critical_leaks is True
        assert any(f.category == "stripe_api_key" for f in report.findings)
        assert any(f.category == "canary" for f in report.findings)
