"""
Secret scanner engine using regex patterns and Shannon entropy analysis.
Detects API keys, private keys, database URIs, JWTs, emails, IPs and high-entropy secrets.
"""

from __future__ import annotations

import collections
import math
import re
from pathlib import Path
from typing import List, Optional
from ..models import SecretFinding

# Secret patterns
PATTERNS = [
    (
        "private_key",
        "Private Cryptographic Key Header",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),
        "CRITICAL",
    ),
    (
        "aws_access_key",
        "AWS Access Key ID",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "CRITICAL",
    ),
    (
        "aws_secret_key",
        "AWS Secret Access Key",
        re.compile(r"(?i)\baws(?:_secret_access_key|_secret)?\s*[:=]\s*['\"]([0-9a-zA-Z/+]{40})['\"]"),
        "CRITICAL",
    ),
    (
        "stripe_api_key",
        "Stripe API Key",
        re.compile(r"\b(?:sk|pk)_(?:test|live)_[0-9a-zA-Z_]{10,}\b"),
        "CRITICAL",
    ),
    (
        "github_token",
        "GitHub Personal Access Token",
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[0-9a-zA-Z]{36,}\b"),
        "HIGH",
    ),
    (
        "google_api_key",
        "Google Cloud API Key",
        re.compile(r"\bAIza[0-9A-Za-z\-_]{30,45}\b"),
        "HIGH",
    ),
    (
        "jwt_token",
        "JSON Web Token (JWT)",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
        "HIGH",
    ),
    (
        "database_uri",
        "Database Connection URI with Credentials",
        re.compile(r"(?:postgres|postgresql|mysql|mongodb|redis|mssql|oracle):\/\/[^\s:]+:([^\s@]+)@[^\s\/]+", re.IGNORECASE),
        "CRITICAL",
    ),
    (
        "private_ip",
        "Internal / Private IP Address",
        re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b"),
        "MEDIUM",
    ),
    (
        "internal_url",
        "Internal Corporate Endpoint URL",
        re.compile(r"https?:\/\/(?:[a-zA-Z0-9-]+\.)*(?:corp|internal|local|lan|intra|priv)\b[^\s\"']*"),
        "MEDIUM",
    ),
    (
        "email_address",
        "Plaintext Email Address",
        re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b"),
        "LOW",
    ),
]

IGNORE_EMAIL_DOMAINS = {"example.com", "example.org", "test.com", "localhost", "schema.org"}


def calculate_shannon_entropy(data: str) -> float:
    """
    Computes Shannon entropy in bits per character:
    H = -sum(p * log2(p))
    """
    if not data:
        return 0.0
    length = len(data)
    counts = collections.Counter(data)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def mask_secret(text: str) -> str:
    """Masks secret preserving prefix and suffix for debugging."""
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}...{text[-4:]}"


class SecretScanner:
    """
    Scanner detecting credentials, private keys, tokens and high-entropy secrets.
    """

    def __init__(self, entropy_threshold: float = 4.5, min_entropy_length: int = 20):
        self.entropy_threshold = entropy_threshold
        self.min_entropy_length = min_entropy_length

    def scan_text(self, text: str, file_path: str = "") -> List[SecretFinding]:
        """
        Scans a text string line by line for secret patterns and high entropy.
        """
        findings: List[SecretFinding] = []
        lines = text.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "/*", "*", "#")):
                # Check for private keys even in comment banners
                if "BEGIN" not in line and "PRIVATE KEY" not in line and "API" not in line and "sk_" not in line:
                    continue

            # 1. Regex pattern scans
            for cat, desc, pattern, severity in PATTERNS:
                for match in pattern.finditer(line):
                    matched_str = match.group(0)

                    # Filter out benign test email domains
                    if cat == "email_address":
                        domain = matched_str.split("@")[-1].lower()
                        if domain in IGNORE_EMAIL_DOMAINS:
                            continue

                    # Filter out benign localhost / dummy IPs
                    if cat == "private_ip" and (matched_str.startswith("127.") or matched_str == "0.0.0.0"):
                        continue

                    findings.append(
                        SecretFinding(
                            file_path=file_path,
                            line_number=line_idx,
                            category=cat,
                            description=desc,
                            matched_text=mask_secret(matched_str),
                            severity=severity,
                        )
                    )

            # 2. Shannon entropy analysis on candidate tokens
            tokens = re.findall(r"\b[A-Za-z0-9_+\/=-]{20,}\b", line)
            for token in tokens:
                # Ignore tokens already caught by regex
                if any(token in f.matched_text for f in findings if f.line_number == line_idx):
                    continue

                # Skip repetitive patterns
                if len(set(token)) < 8:
                    continue

                entropy = calculate_shannon_entropy(token)

                # Hex tokens (max theoretical entropy is 4.0 bits)
                is_hex = all(c in "0123456789abcdefABCDEF" for c in token)
                threshold = 3.2 if is_hex else self.entropy_threshold

                if entropy >= threshold:
                    findings.append(
                        SecretFinding(
                            file_path=file_path,
                            line_number=line_idx,
                            category="high_entropy",
                            description=f"High-Entropy {'Hex ' if is_hex else ''}Secret Token ({entropy:.2f} bits/char)",
                            matched_text=mask_secret(token),
                            entropy=round(entropy, 2),
                            severity="MEDIUM",
                        )
                    )

        return findings

    def scan_file(self, file_path: Path, rel_path: Optional[str] = None) -> List[SecretFinding]:
        """
        Reads and scans a single text file.
        """
        target = file_path.resolve()
        display_path = rel_path or target.name

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return self.scan_text(content, file_path=display_path)
        except Exception as e:
            return [
                SecretFinding(
                    file_path=display_path,
                    line_number=1,
                    category="read_error",
                    description=f"Unable to read file: {e}",
                    matched_text="",
                    severity="LOW",
                )
            ]
