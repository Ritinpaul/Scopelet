"""
Canary detection scanner verifying that seeded or configured canaries are detected before export.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Set
from ..models import SecretFinding

DEFAULT_CANARY_PATTERNS = [
    re.compile(r"\bCANARY_[A-Za-z0-9_]+\b"),
    re.compile(r"\b(?:CONFIDENTIAL|PROPRIETARY)_[A-Za-z0-9_]+\b"),
]


class CanaryScanner:
    """
    Scans content against configured canary strings and regex patterns.
    """

    def __init__(
        self,
        canaries: Optional[Set[str]] = None,
        patterns: Optional[List[re.Pattern[str]]] = None,
    ):
        self.canaries: Set[str] = set(canaries or set())
        self.patterns: List[re.Pattern[str]] = patterns or list(DEFAULT_CANARY_PATTERNS)

    def add_canary(self, canary: str) -> None:
        """Registers a known canary string."""
        if canary.strip():
            self.canaries.add(canary.strip())

    def scan_text(self, text: str, file_path: str = "") -> List[SecretFinding]:
        """
        Scans text line-by-line for exact canary matches and canary patterns.
        """
        findings: List[SecretFinding] = []
        lines = text.splitlines()

        for line_idx, line in enumerate(lines, start=1):
            # 1. Exact string matches
            for canary in self.canaries:
                if canary in line:
                    findings.append(
                        SecretFinding(
                            file_path=file_path,
                            line_number=line_idx,
                            category="canary",
                            description=f"Configured Canary Token Detected: {canary[:8]}...",
                            matched_text=canary[:6] + "...",
                            severity="CRITICAL",
                        )
                    )

            # 2. Canary pattern matches
            for pattern in self.patterns:
                for match in pattern.finditer(line):
                    matched = match.group(0)
                    if matched not in self.canaries:
                        findings.append(
                            SecretFinding(
                                file_path=file_path,
                                line_number=line_idx,
                                category="canary",
                                description=f"Seeded Canary Pattern Detected: {matched[:8]}...",
                                matched_text=matched[:6] + "...",
                                severity="CRITICAL",
                            )
                        )

        return findings

    def scan_file(self, file_path: Path, rel_path: Optional[str] = None) -> List[SecretFinding]:
        """
        Reads and scans a file for canaries.
        """
        target = file_path.resolve()
        display_path = rel_path or target.name
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return self.scan_text(content, file_path=display_path)
        except Exception:
            return []
