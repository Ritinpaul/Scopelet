"""
Privacy Report Generator.
Aggregates scanner and sanitizer outcomes to generate honest, non-misleading privacy disclosures.
Computes token-level source overlap and disclosure minimization statistics.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import shutil
from pydantic import BaseModel, Field

import tree_sitter
import tree_sitter_typescript

from ..privacy.scanner.orchestrator import PrivacyScanner
from ..capsule.packager import CapsulePackager

IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".scopelet",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
    ".vitest",
}

IDENTIFIER_NODE_TYPES = {
    "identifier",
    "property_identifier",
    "type_identifier",
    "shorthand_property_identifier",
    "shorthand_property_identifier_pattern",
    "statement_identifier",
}


class PrivacyReportData(BaseModel):
    """Data model containing all privacy and disclosure metrics."""
    original_files: int = 0
    capsule_files: int = 0
    original_loc: int = 0
    capsule_loc: int = 0
    known_secret_patterns: int = 0
    configured_canaries: int = 0
    email_addresses: int = 0
    internal_urls: int = 0
    original_identifiers_retained: int = 0
    original_string_literals_retained: int = 0
    potential_proprietary_terms: int = 0
    source_overlap_pct: float = 0.0
    manual_review: str = "REQUIRED"
    disclaimer: List[str] = Field(
        default_factory=lambda: [
            "Scopelet minimizes disclosure.",
            "It does not mathematically guarantee confidentiality.",
        ]
    )

    def format_text(self) -> str:
        """
        Renders the standard Scopelet Privacy Report format.
        """
        rows = [
            ("Original files", str(self.original_files)),
            ("Capsule files", str(self.capsule_files)),
            ("Original LOC", f"{self.original_loc:,}"),
            ("Capsule LOC", f"{self.capsule_loc:,}"),
            ("Known secret patterns", str(self.known_secret_patterns)),
            ("Configured canaries", str(self.configured_canaries)),
            ("Email addresses", str(self.email_addresses)),
            ("Internal URLs", str(self.internal_urls)),
            ("Original identifiers retained", str(self.original_identifiers_retained)),
            ("Original string literals retained", str(self.original_string_literals_retained)),
            ("Potential proprietary terms", str(self.potential_proprietary_terms)),
            ("Source overlap", f"{self.source_overlap_pct:.1f}%"),
        ]

        lines = [
            "Scopelet Privacy Report",
            "",
        ]
        for label, val in rows:
            sp = " " * max(2, 37 - len(label) - len(val))
            lines.append(label + sp + val)

        lines.extend([
            "",
            f"Manual review: {self.manual_review}",
            "",
            self.disclaimer[0],
            self.disclaimer[1],
        ])
        return "\n".join(lines)


class PrivacyReportGenerator:
    """
    Computes source overlap and privacy metrics comparing original workspace with capsule.
    """

    def __init__(
        self,
        canaries: Optional[Set[str]] = None,
        entropy_threshold: float = 4.5,
    ):
        self.canaries = canaries or set()
        self.entropy_threshold = entropy_threshold
        self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
        self.tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
        self.ts_parser = tree_sitter.Parser(self.ts_lang)
        self.tsx_parser = tree_sitter.Parser(self.tsx_lang)
        self.scanner = PrivacyScanner(canaries=self.canaries, entropy_threshold=self.entropy_threshold)

    def _collect_files(self, root_dir: Path) -> List[Path]:
        """Collects all relevant source and configuration files in a directory."""
        files: List[Path] = []
        root = root_dir.resolve()
        for item in sorted(root.rglob("*")):
            if not item.is_file():
                continue
            rel_parts = item.relative_to(root).parts
            if any(part in IGNORE_DIRS for part in rel_parts):
                continue
            files.append(item)
        return files

    def _count_loc(self, files: List[Path]) -> int:
        """Counts total lines of code across files."""
        total = 0
        for f in files:
            try:
                total += len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                pass
        return total

    def extract_tokens(self, file_path: Path) -> Tuple[Set[str], Set[str]]:
        """
        Extracts identifiers and string literals from a source file using Tree-sitter.
        Returns: (identifiers_set, strings_set)
        """
        identifiers: Set[str] = set()
        strings: Set[str] = set()

        if file_path.suffix not in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            return identifiers, strings

        try:
            code_bytes = file_path.read_bytes()
        except Exception:
            return identifiers, strings

        parser = self.tsx_parser if file_path.suffix in (".tsx", ".jsx") else self.ts_parser
        tree = parser.parse(code_bytes)

        def visit(node: tree_sitter.Node) -> None:
            if node.type in IDENTIFIER_NODE_TYPES:
                text = node.text.decode("utf-8", errors="replace").strip()
                if text:
                    identifiers.add(text)
            elif node.type == "string_fragment":
                text = node.text.decode("utf-8", errors="replace").strip()
                if text:
                    strings.add(text)
            elif node.type == "string" and len(node.children) == 0:
                text = node.text.decode("utf-8", errors="replace").strip("'\"` ")
                if text:
                    strings.add(text)

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return identifiers, strings

    def collect_tokens_for_directory(self, root_dir: Path) -> Tuple[Set[str], Set[str]]:
        """
        Collects all identifiers and string literals across all files in root_dir.
        """
        all_identifiers: Set[str] = set()
        all_strings: Set[str] = set()

        for f in self._collect_files(root_dir):
            ids, strs = self.extract_tokens(f)
            all_identifiers.update(ids)
            all_strings.update(strs)

        return all_identifiers, all_strings

    def generate_report(
        self,
        original_dir: Path,
        capsule_target: Path,
    ) -> PrivacyReportData:
        """
        Generates PrivacyReportData comparing original workspace against a capsule directory or .scopelet file.
        """
        resolved_orig = original_dir.resolve()
        resolved_capsule = capsule_target.resolve()

        is_temp = False
        if resolved_capsule.is_file() and resolved_capsule.suffix == ".scopelet":
            staging = Path(tempfile.mkdtemp(prefix="scopelet_report_"))
            CapsulePackager.unpack(resolved_capsule, staging)
            capsule_dir = staging
            is_temp = True
        elif resolved_capsule.is_dir():
            capsule_dir = resolved_capsule
        else:
            raise FileNotFoundError(f"Capsule target not found: {capsule_target}")

        try:
            orig_files = self._collect_files(resolved_orig)
            cap_files = self._collect_files(capsule_dir)

            orig_file_count = len(orig_files)
            cap_file_count = len(cap_files)

            orig_loc = self._count_loc(orig_files)
            cap_loc = self._count_loc(cap_files)

            # Extract tokens
            orig_ids, orig_strs = self.collect_tokens_for_directory(resolved_orig)
            cap_ids, cap_strs = self.collect_tokens_for_directory(capsule_dir)

            orig_tokens = orig_ids | orig_strs
            cap_tokens = cap_ids | cap_strs

            retained_ids = cap_ids & orig_ids
            retained_strs = cap_strs & orig_strs
            intersection_tokens = cap_tokens & orig_tokens

            if len(orig_tokens) > 0:
                overlap_pct = (len(intersection_tokens) / len(orig_tokens)) * 100.0
            else:
                overlap_pct = 0.0

            # Scan capsule target for privacy leaks
            scan_report = self.scanner.scan(capsule_dir)

            known_secrets = 0
            configured_canaries = 0
            email_addresses = 0
            internal_urls = 0
            proprietary_terms = 0

            for finding in scan_report.findings:
                cat = finding.category
                if cat in (
                    "aws_access_key",
                    "aws_secret_key",
                    "stripe_api_key",
                    "github_token",
                    "google_api_key",
                    "private_key",
                    "database_uri",
                    "jwt_token",
                    "high_entropy_secret",
                ):
                    known_secrets += 1
                elif cat == "canary":
                    configured_canaries += 1
                elif cat == "sensitive_email":
                    email_addresses += 1
                elif cat in ("private_ip", "internal_url"):
                    internal_urls += 1
                elif cat == "semantic_proprietary":
                    proprietary_terms += 1

            return PrivacyReportData(
                original_files=orig_file_count,
                capsule_files=cap_file_count,
                original_loc=orig_loc,
                capsule_loc=cap_loc,
                known_secret_patterns=known_secrets,
                configured_canaries=configured_canaries,
                email_addresses=email_addresses,
                internal_urls=internal_urls,
                original_identifiers_retained=len(retained_ids),
                original_string_literals_retained=len(retained_strs),
                potential_proprietary_terms=proprietary_terms,
                source_overlap_pct=round(overlap_pct, 1),
                manual_review="REQUIRED",
            )
        finally:
            if is_temp:
                shutil.rmtree(capsule_dir, ignore_errors=True)
