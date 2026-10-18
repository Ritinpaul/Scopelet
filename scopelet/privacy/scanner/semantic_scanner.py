"""
Semantic identifier classifier for identifying proprietary, personal and business sensitive code symbols.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional
from ..models import Sensitivity, SecretFinding

# Patterns for semantic sensitivity
PROPRIETARY_PATTERNS = [
    re.compile(r"\bCUSTOMER_PROJECT_[A-Za-z0-9_]+\b", re.IGNORECASE),
    re.compile(r"\bPROJECT_[A-Z0-9_]{3,}\b"),
    re.compile(r"\b(?:PROPRIETARY|INTERNAL|CONFIDENTIAL)_[A-Za-z0-9_]+\b"),
    re.compile(r"\b(?:GOLDMAN|CITI|JPMORGAN|BARCLAYS)_[A-Za-z0-9_]+\b", re.IGNORECASE),
]

PERSONAL_INFO_PATTERNS = [
    re.compile(r"(?:^|_|\b)(?:ssn|social_security|passport_num|national_id)(?:_|\b|$)", re.IGNORECASE),
    re.compile(r"(?:^|_|\b)(?:credit_card_num|card_cvv|bank_account_num)(?:_|\b|$)", re.IGNORECASE),
    re.compile(r"(?:^|_|\b)(?:date_of_birth|home_address|patient_record)(?:_|\b|$)", re.IGNORECASE),
]

BUSINESS_SENSITIVE_PATTERNS = [
    re.compile(r"(?:^|_|\b)(?:pricing_model|margin_rate|commission_rate|acquisition_target)(?:_|\b|$)", re.IGNORECASE),
    re.compile(r"(?:^|_|\b)(?:hedge_strategy|revenue_forecast|secret_formula)(?:_|\b|$)", re.IGNORECASE),
]


class SemanticScanner:
    """
    Scans code identifiers and strings to classify sensitivity levels.
    """

    def classify_identifier(self, identifier: str) -> Sensitivity:
        """
        Classifies an identifier or symbol into a Sensitivity category.
        """
        for pat in PROPRIETARY_PATTERNS:
            if pat.search(identifier):
                return Sensitivity.POTENTIALLY_PROPRIETARY

        for pat in PERSONAL_INFO_PATTERNS:
            if pat.search(identifier):
                return Sensitivity.PERSONAL_INFORMATION

        for pat in BUSINESS_SENSITIVE_PATTERNS:
            if pat.search(identifier):
                return Sensitivity.BUSINESS_SENSITIVE

        # Generic common names are safe
        if identifier.lower() in (
            "id", "name", "date", "service", "timestamp", "item", "user",
            "calculate", "result", "error", "options", "config", "status"
        ):
            return Sensitivity.SAFE

        return Sensitivity.UNKNOWN

    def scan_text(self, text: str, file_path: str = "") -> List[SecretFinding]:
        """
        Scans text line-by-line for proprietary, personal and business sensitive identifiers.
        """
        findings: List[SecretFinding] = []
        lines = text.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            # Check proprietary patterns
            for pat in PROPRIETARY_PATTERNS:
                for match in pat.finditer(line):
                    matched = match.group(0)
                    findings.append(
                        SecretFinding(
                            file_path=file_path,
                            line_number=line_idx,
                            category="semantic_proprietary",
                            description=f"Potentially Proprietary Identifier: {matched}",
                            matched_text=matched,
                            severity="HIGH",
                        )
                    )

            # Check personal information patterns
            for pat in PERSONAL_INFO_PATTERNS:
                for match in pat.finditer(line):
                    matched = match.group(0)
                    findings.append(
                        SecretFinding(
                            file_path=file_path,
                            line_number=line_idx,
                            category="semantic_pii",
                            description=f"Personal Information Identifier: {matched}",
                            matched_text=matched,
                            severity="HIGH",
                        )
                    )

            # Check business sensitive patterns
            for pat in BUSINESS_SENSITIVE_PATTERNS:
                for match in pat.finditer(line):
                    matched = match.group(0)
                    findings.append(
                        SecretFinding(
                            file_path=file_path,
                            line_number=line_idx,
                            category="semantic_business",
                            description=f"Business Sensitive Identifier: {matched}",
                            matched_text=matched,
                            severity="MEDIUM",
                        )
                    )

        return findings

    def scan_file(self, file_path: Path, rel_path: Optional[str] = None) -> List[SecretFinding]:
        """
        Reads and scans a file for semantic sensitivity.
        """
        target = file_path.resolve()
        display_path = rel_path or target.name
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return self.scan_text(content, file_path=display_path)
        except Exception:
            return []
