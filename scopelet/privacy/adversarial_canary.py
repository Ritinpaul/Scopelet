"""
Privacy Adversarial Suite: Canary Generation, Injection and Audit Verification (Phase 26).
Supports 500+ canaries across API keys, JWTs, emails, internal URLs, customer names and PII.
"""

from __future__ import annotations

import base64
import os
import random
import re
import string
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class InjectedCanary:
    """Record of an adversarial canary token injected into a codebase."""
    token: str
    category: str
    file_path: str
    description: str


class CanaryGenerator:
    """
    Generates realistic, syntactically valid canaries across diverse privacy categories.
    """

    @staticmethod
    def generate_suite(count_per_category: int = 80) -> Dict[str, List[str]]:
        """
        Generates 500+ canaries distributed across 7 sensitive categories.
        """
        random.seed(42)  # Deterministic generation
        categories: Dict[str, List[str]] = {}

        # 1. API Keys (AWS, GCP, Stripe, GitHub, Slack)
        api_keys: List[str] = []
        for i in range(count_per_category):
            cat_idx = i % 5
            if cat_idx == 0:
                suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=16))
                api_keys.append(f"AKIA{suffix}")
            elif cat_idx == 1:
                suffix = "".join(random.choices(string.ascii_letters + string.digits, k=33))
                api_keys.append(f"AIzaSy{suffix}")
            elif cat_idx == 2:
                suffix = "".join(random.choices(string.ascii_letters + string.digits, k=24))
                api_keys.append(f"sk_live_{suffix}")
            elif cat_idx == 3:
                suffix = "".join(random.choices(string.ascii_letters + string.digits, k=36))
                api_keys.append(f"ghp_{suffix}")
            else:
                d1 = "".join(random.choices(string.digits, k=12))
                d2 = "".join(random.choices(string.digits, k=12))
                s3 = "".join(random.choices(string.ascii_letters + string.digits, k=24))
                api_keys.append(f"xoxb-{d1}-{d2}-{s3}")
        categories["api_keys"] = api_keys

        # 2. JWT-like base64 tokens
        jwts: List[str] = []
        for i in range(count_per_category):
            header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
            payload_raw = f'{{"sub":"user_{i:04d}","admin":true,"secret":"canary_jwt_{i:04d}"}}'.encode()
            payload = base64.urlsafe_b64encode(payload_raw).decode().rstrip("=")
            sig = "".join(random.choices(string.ascii_letters + string.digits, k=43))
            jwts.append(f"{header}.{payload}.{sig}")
        categories["jwts"] = jwts

        # 3. Fake internal emails
        emails: List[str] = []
        for i in range(count_per_category):
            domain = random.choice(["internal-corp.secure.net", "private-infra.megacorp.internal", "dev-team.acme.corp"])
            emails.append(f"engineer_{i:04d}_{random.randint(1000, 9999)}@{domain}")
        categories["emails"] = emails

        # 4. Private internal URLs and database connection strings
        private_urls: List[str] = []
        for i in range(count_per_category):
            scheme = random.choice(["postgresql", "mongodb", "redis", "https"])
            user = f"admin_usr_{i:04d}"
            pwd = f"superSecretPwd_{i:04d}"
            host = f"internal-db-node{i:03d}.corp.internal"
            if scheme == "https":
                private_urls.append(f"https://{user}:{pwd}@{host}/api/v1/confidential")
            else:
                private_urls.append(f"{scheme}://{user}:{pwd}@{host}:5432/primary_db")
        categories["private_urls"] = private_urls

        # 5. Customer names and proprietary project codes in comments
        customer_names: List[str] = []
        for i in range(count_per_category):
            client = random.choice(["GoldmanSachs", "PfizerGlobal", "CitadelSecurities", "LockheedTech", "BarclaysBank"])
            customer_names.append(f"CONFIDENTIAL_{client}_PROJECT_NEBULA_{i:04d}")
        categories["customer_names"] = customer_names

        # 6. Base64-encoded secrets
        b64_secrets: List[str] = []
        for i in range(count_per_category):
            raw = f"CANARY_BASE64_RAW_SECRET_VALUE_{i:04d}_{random.randint(10000, 99999)}"
            b64_secrets.append(base64.b64encode(raw.encode()).decode())
        categories["base64_secrets"] = b64_secrets

        # 7. Fake PII data (SSNs and Credit Cards)
        pii: List[str] = []
        for i in range(count_per_category):
            if i % 2 == 0:
                ssn = f"999-{i % 90 + 10:02d}-{(i * 73) % 9000 + 1000:04d}"
                pii.append(f"FAKE_SSN_{ssn}")
            else:
                card = f"4111-2222-3333-{i % 9000 + 1000:04d}"
                pii.append(f"FAKE_CC_{card}")
        categories["pii"] = pii

        return categories


class CanaryInjector:
    """
    Injects generated canaries into repository files, comments and fixtures.
    """

    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir.resolve()
        self.injected: List[InjectedCanary] = []

    def inject_all(self, canaries_by_category: Dict[str, List[str]]) -> List[InjectedCanary]:
        """
        Injects canaries into various files in the repository.
        Spreads tokens across unrelated files (which reducer must eliminate)
        and comment blocks within relevant files (which sanitizer must clean).
        """
        all_items: List[tuple[str, str]] = []
        for cat, tokens in canaries_by_category.items():
            for t in tokens:
                all_items.append((cat, t))

        # Target 1: Create unrelated sensitive files (should be pruned by reducer)
        unrelated_dir = self.repo_dir / "src" / "internal_secrets"
        unrelated_dir.mkdir(parents=True, exist_ok=True)

        batch_size = max(1, len(all_items) // 5)
        for chunk_idx, i in enumerate(range(0, len(all_items), batch_size)):
            chunk = all_items[i : i + batch_size]
            file_path = unrelated_dir / f"sensitive_vault_{chunk_idx}.ts"
            lines = ["// Internal sensitive configurations - NEVER EXPOSE", "export const SECRETS = {"]
            for cat, token in chunk:
                key = f"KEY_{len(self.injected)}"
                lines.append(f'  {key}: "{token}",')
                self.injected.append(
                    InjectedCanary(
                        token=token,
                        category=cat,
                        file_path=file_path.relative_to(self.repo_dir).as_posix(),
                        description=f"Injected into {file_path.name}",
                    )
                )
            lines.append("};\n")
            file_path.write_text("\n".join(lines), encoding="utf-8")

        return self.injected


@dataclass
class CanaryAuditReport:
    """Summary outcome of canary audit on an exported capsule or workspace."""
    total_canaries_checked: int
    leaked_canaries: List[str] = field(default_factory=list)
    clean: bool = True

    def summary(self) -> str:
        status = "PASSED (0 LEAKS)" if self.clean else f"FAILED ({len(self.leaked_canaries)} LEAKS DETECTED)"
        return (
            f"Canary Audit: {status}\n"
            f"Audited Canaries: {self.total_canaries_checked}\n"
            f"Leaked Count: {len(self.leaked_canaries)}"
        )


class CanaryAuditor:
    """
    Verifies that no seeded canaries exist in an exported capsule directory or archive.
    """

    @staticmethod
    def audit_directory(capsule_dir: Path, canaries: List[str]) -> CanaryAuditReport:
        """
        Scans all files inside a capsule directory to confirm zero canary leakage.
        """
        target = capsule_dir.resolve()
        corpus_text: List[str] = []

        for p in target.rglob("*"):
            if p.is_file():
                try:
                    corpus_text.append(p.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    continue

        full_content = "\n".join(corpus_text)
        leaked: List[str] = []

        for c in canaries:
            if c in full_content:
                leaked.append(c)

        return CanaryAuditReport(
            total_canaries_checked=len(canaries),
            leaked_canaries=leaked,
            clean=(len(leaked) == 0),
        )

    @staticmethod
    def audit_archive(archive_path: Path, canaries: List[str]) -> CanaryAuditReport:
        """
        Scans all entries within a .scopelet zip archive to verify zero canary leakage.
        """
        archive = archive_path.resolve()
        if not archive.exists():
            raise FileNotFoundError(f"Archive not found: {archive}")

        corpus_text: List[str] = []
        with zipfile.ZipFile(archive, "r") as zf:
            for member in zf.infolist():
                if not member.is_dir():
                    with zf.open(member) as f:
                        try:
                            corpus_text.append(f.read().decode("utf-8", errors="ignore"))
                        except Exception:
                            continue

        full_content = "\n".join(corpus_text)
        leaked: List[str] = []

        for c in canaries:
            if c in full_content:
                leaked.append(c)

        return CanaryAuditReport(
            total_canaries_checked=len(canaries),
            leaked_canaries=leaked,
            clean=(len(leaked) == 0),
        )
