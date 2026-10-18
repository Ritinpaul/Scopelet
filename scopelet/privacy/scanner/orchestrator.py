"""
Consolidated privacy scanner orchestrating secret, canary, git leak and semantic scanners.
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
from typing import List, Optional, Set
import shutil

from ..models import ScanReport, SecretFinding
from .secret_scanner import SecretScanner
from .canary_scanner import CanaryScanner
from .git_scanner import GitScanner
from .semantic_scanner import SemanticScanner
from ...capsule.packager import CapsulePackager

IGNORE_SCAN_DIRS = {
    "node_modules",
    ".pytest_cache",
    "__pycache__",
    "dist",
    "build",
}


class PrivacyScanner:
    """
    Unified privacy and secret scanning orchestrator for Scopelet capsules and source trees.
    """

    def __init__(
        self,
        canaries: Optional[Set[str]] = None,
        entropy_threshold: float = 4.5,
    ):
        self.secret_scanner = SecretScanner(entropy_threshold=entropy_threshold)
        self.canary_scanner = CanaryScanner(canaries=canaries)
        self.git_scanner = GitScanner()
        self.semantic_scanner = SemanticScanner()

    def scan(self, target: Path) -> ScanReport:
        """
        Scans a directory or .scopelet archive for all categories of privacy leaks.
        """
        resolved = target.resolve()
        is_temp = False

        if resolved.is_file() and resolved.suffix == ".scopelet":
            staging = Path(tempfile.mkdtemp(prefix="scopelet_scan_"))
            CapsulePackager.unpack(resolved, staging)
            scan_dir = staging
            is_temp = True
        elif resolved.is_dir():
            scan_dir = resolved
        else:
            raise FileNotFoundError(f"Target path not found: {target}")

        try:
            findings: List[SecretFinding] = []

            # 1. Check for git repository history leaks
            findings.extend(self.git_scanner.scan_directory(scan_dir))

            # 2. Iterate and scan all regular source and configuration files
            total_files = 0
            for file_path in sorted(scan_dir.rglob("*")):
                if file_path.is_file():
                    rel_parts = file_path.relative_to(scan_dir).parts
                    if any(part in IGNORE_SCAN_DIRS for part in rel_parts):
                        continue

                    rel_posix = file_path.relative_to(scan_dir).as_posix()
                    total_files += 1

                    # Secret pattern & entropy scan
                    findings.extend(self.secret_scanner.scan_file(file_path, rel_path=rel_posix))

                    # Canary scan
                    findings.extend(self.canary_scanner.scan_file(file_path, rel_path=rel_posix))

                    # Semantic sensitivity scan
                    findings.extend(self.semantic_scanner.scan_file(file_path, rel_path=rel_posix))

            now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
            has_critical = any(f.severity in ("CRITICAL", "HIGH") for f in findings)

            return ScanReport(
                target_path=str(resolved),
                total_files_scanned=total_files,
                findings=findings,
                has_critical_leaks=has_critical,
                scanned_at=now_utc,
            )
        finally:
            if is_temp:
                shutil.rmtree(scan_dir, ignore_errors=True)
