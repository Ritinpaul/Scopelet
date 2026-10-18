"""
Privacy adversarial test suite (Phase 26).
Seeds 500+ canaries across 7 categories and validates that zero canaries leak into exported capsules.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path
import pytest

from scopelet.capsule.builder import CapsuleBuilder
from scopelet.capsule.packager import CapsulePackager
from scopelet.privacy.adversarial_canary import (
    CanaryAuditor,
    CanaryGenerator,
    CanaryInjector,
)
from scopelet.privacy.scanner.canary_scanner import CanaryScanner
from scopelet.privacy.scanner.secret_scanner import SecretScanner
from scopelet.reducer.candidate import CandidateState


def test_canary_generator_creates_500_plus_tokens():
    """Validates that CanaryGenerator generates at least 500 canaries across all categories."""
    suite = CanaryGenerator.generate_suite(count_per_category=80)
    expected_categories = {
        "api_keys",
        "jwts",
        "emails",
        "private_urls",
        "customer_names",
        "base64_secrets",
        "pii",
    }
    assert expected_categories.issubset(set(suite.keys()))

    total_tokens = sum(len(tokens) for tokens in suite.values())
    assert total_tokens >= 500, f"Expected >= 500 canaries, got {total_tokens}"
    for cat in expected_categories:
        assert len(suite[cat]) >= 70, f"Category {cat} should have at least 70 canaries"


def test_canary_categories_syntax_validation():
    """Validates syntactic validity of generated canaries."""
    suite = CanaryGenerator.generate_suite(count_per_category=10)

    # API keys validation
    api_keys = suite["api_keys"]
    assert any(k.startswith("AKIA") for k in api_keys)
    assert any(k.startswith("AIzaSy") for k in api_keys)
    assert any(k.startswith("sk_live_") for k in api_keys)
    assert any(k.startswith("ghp_") for k in api_keys)
    assert any(k.startswith("xoxb-") for k in api_keys)

    # JWT validation
    for jwt in suite["jwts"]:
        parts = jwt.split(".")
        assert len(parts) == 3, f"Invalid JWT structure: {jwt}"

    # Email validation
    for email in suite["emails"]:
        assert "@" in email
        assert "." in email.split("@")[1]

    # Private URLs validation
    for url in suite["private_urls"]:
        assert "://" in url
        assert "@" in url

    # Customer names validation
    for cname in suite["customer_names"]:
        assert "CONFIDENTIAL_" in cname
        assert "PROJECT_NEBULA" in cname


def test_canary_scanner_detects_seeded_canaries():
    """Validates that CanaryScanner detects seeded canaries in text."""
    suite = CanaryGenerator.generate_suite(count_per_category=5)
    scanner = CanaryScanner()

    all_tokens = []
    for tokens in suite.values():
        all_tokens.extend(tokens)
        for t in tokens:
            scanner.add_canary(t)

    sample_doc = "\n".join(f"const config_{i} = '{token}';" for i, token in enumerate(all_tokens[:20]))
    findings = scanner.scan_text(sample_doc, file_path="config.ts")

    assert len(findings) >= 20
    assert all(f.category == "canary" for f in findings)
    assert all(f.severity == "CRITICAL" for f in findings)


def test_canary_auditor_detects_intentional_leak(tmp_path):
    """Validates that CanaryAuditor immediately flags any canary present in an archive."""
    test_canary = "AKIAEXAMPLELEAKEDCANARYTOKEN123"
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir()
    (stage_dir / "leaky.txt").write_text(f"Key is {test_canary}", encoding="utf-8")

    archive_path = tmp_path / "leaky.scopelet"
    CapsulePackager.pack(stage_dir, archive_path)

    report = CanaryAuditor.audit_archive(archive_path, [test_canary, "UNLEAKED_CANARY_TOKEN"])
    assert report.clean is False
    assert test_canary in report.leaked_canaries
    assert "UNLEAKED_CANARY_TOKEN" not in report.leaked_canaries


def test_privacy_adversarial_suite_zero_leaks_on_minimized_capsule(tmp_path):
    """
    Seeds a workspace with 500+ canaries across 7 categories.
    Executes reduction and packaging.
    Asserts: for canary in all_seeded_canaries: assert canary not in exported_capsule_contents.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # 1. Essential defect reproduction files
    (repo_dir / "src").mkdir()
    (repo_dir / "src" / "math.ts").write_text(
        "export function add(a: number, b: number): number {\n  return a + b;\n}\n",
        encoding="utf-8",
    )
    (repo_dir / "package.json").write_text('{"name": "canary-test"}\n', encoding="utf-8")

    # 2. Seed 500+ canaries into unrelated sensitive modules
    suite = CanaryGenerator.generate_suite(count_per_category=75)
    all_canaries: List[str] = []
    for tokens in suite.values():
        all_canaries.extend(tokens)
    assert len(all_canaries) >= 500

    injector = CanaryInjector(repo_dir=repo_dir)
    injected_records = injector.inject_all(suite)
    assert len(injected_records) >= 500

    # 3. Simulate minimization where only defect files are kept
    kept_files = {"src/math.ts", "package.json"}
    state = CandidateState(root_dir=repo_dir, active_files=kept_files)

    # 4. Build and package reproduction capsule
    capsule_ws = tmp_path / "capsule_ws"
    builder = CapsuleBuilder()
    builder.build(
        output_dir=capsule_ws,
        state=state,
        title="Canary Adversarial Verification",
        command="npm test",
        failure_fingerprint="fp_canary_test",
    )

    archive_path = tmp_path / "adversarial_output.scopelet"
    CapsulePackager.pack(capsule_ws, archive_path)
    assert archive_path.exists()

    # 5. Extract all textual content from the exported capsule
    corpus_text: List[str] = []
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            if not member.is_dir():
                with zf.open(member) as f:
                    corpus_text.append(f.read().decode("utf-8", errors="ignore"))
    exported_capsule_contents = "\n".join(corpus_text)

    # 6. Authoritative privacy adversarial check: Zero leaks across all 500+ canaries
    report = CanaryAuditor.audit_archive(archive_path, all_canaries)
    assert report.clean is True
    assert len(report.leaked_canaries) == 0

    for canary in all_canaries:
        assert canary not in exported_capsule_contents
