"""
Behavior-preserving sanitizer engine.
Sequentially transforms sensitive identifiers and verifies failure fingerprint preservation after each rename.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ...runner import IsolatedRunner
from ..scanner.semantic_scanner import SemanticScanner, PROPRIETARY_PATTERNS
from ..scanner.canary_scanner import CanaryScanner, DEFAULT_CANARY_PATTERNS
from .renamer import ASTRenamer, IGNORE_DIRS
from .typescript_validator import TypeScriptValidator
from .oracle_check import OracleCheck
from .mapping import MappingStore


class BehaviorPreservingSanitizer:
    """
    Orchestrates atomic AST renames with rollback on syntax errors or failure fingerprint drift.
    """

    def __init__(
        self,
        workspace_dir: Path,
        command: str,
        expected_fingerprint: str,
        runner: Optional[IsolatedRunner] = None,
        private_dir: Optional[Path] = None,
        rename_strings: bool = True,
        strict_type_check: bool = True,
    ):
        self.workspace_dir = workspace_dir.resolve()
        self.command = command
        self.expected_fingerprint = expected_fingerprint
        self.rename_strings = rename_strings
        self.strict_type_check = strict_type_check

        self.renamer = ASTRenamer()
        self.validator = TypeScriptValidator()
        self.oracle_check = OracleCheck(
            command=self.command,
            expected_fingerprint=self.expected_fingerprint,
            runner=runner,
        )
        self.mapping_store = MappingStore(
            private_dir=private_dir or (self.workspace_dir / ".scopelet" / "private")
        )

    def _snapshot_workspace(self) -> Dict[Path, bytes]:
        """Creates an in-memory snapshot of all code files in the workspace."""
        snapshot: Dict[Path, bytes] = {}
        for item in self.workspace_dir.rglob("*"):
            if not item.is_file():
                continue
            rel_parts = item.relative_to(self.workspace_dir).parts
            if any(part in IGNORE_DIRS for part in rel_parts):
                continue
            if item.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json"):
                try:
                    snapshot[item] = item.read_bytes()
                except (OSError, PermissionError):
                    continue
        return snapshot

    def _rollback(self, snapshot: Dict[Path, bytes]) -> None:
        """Restores workspace files to snapshot state."""
        for path, content in snapshot.items():
            try:
                path.write_bytes(content)
            except (OSError, PermissionError):
                pass

    def sanitize_identifier(self, original: str, sanitized: str) -> Tuple[bool, str]:
        """
        Attempts to rename an identifier atomically across the workspace.
        Rolls back if syntax check fails or failure fingerprint changes.
        """
        if original == sanitized:
            return True, "No-op rename"

        snapshot = self._snapshot_workspace()

        # 1. Apply AST renaming
        modifications = self.renamer.rename_directory(
            self.workspace_dir,
            original,
            sanitized,
            rename_strings=self.rename_strings,
        )

        if not modifications:
            return False, f"Identifier '{original}' not found in AST"

        # 2. Syntax & TypeScript Validation
        if self.strict_type_check:
            valid, err_msg = self.validator.validate(self.workspace_dir)
            if not valid:
                self._rollback(snapshot)
                return False, f"Validation rejected: {err_msg}"

        # 3. Oracle Check (Verify fingerprint is preserved)
        oracle_res = self.oracle_check.verify(self.workspace_dir)
        if not oracle_res.is_valid:
            self._rollback(snapshot)
            return False, f"Oracle rejected: {oracle_res.message}"

        # 4. Accepted: record to mapping store
        self.mapping_store.add_mapping(original, sanitized)
        return True, f"Renamed in {len(modifications)} file(s); fingerprint preserved"

    def auto_discover_sensitive_terms(
        self,
        canaries: Optional[Set[str]] = None,
        custom_terms: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Discovers sensitive project identifiers, seeded canaries and custom terms.
        """
        terms: Set[str] = set()

        if canaries:
            terms.update(c.strip() for c in canaries if c.strip())

        if custom_terms:
            terms.update(t.strip() for t in custom_terms if t.strip())

        semantic = SemanticScanner()

        # Scan code files for proprietary pattern matches
        for item in sorted(self.workspace_dir.rglob("*")):
            if not item.is_file():
                continue
            rel_parts = item.relative_to(self.workspace_dir).parts
            if any(part in IGNORE_DIRS for part in rel_parts):
                continue
            if item.suffix in (".ts", ".tsx", ".js", ".jsx"):
                try:
                    text = item.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                for pat in PROPRIETARY_PATTERNS:
                    for match in pat.finditer(text):
                        terms.add(match.group(0))

                for pat in DEFAULT_CANARY_PATTERNS:
                    for match in pat.finditer(text):
                        terms.add(match.group(0))

        return sorted(terms)

    def auto_sanitize(
        self,
        canaries: Optional[Set[str]] = None,
        custom_terms: Optional[List[str]] = None,
        capsule_hash: Optional[str] = None,
    ) -> MappingStore:
        """
        Automatically identifies sensitive terms, generates pseudonyms and performs verified renames.
        """
        terms = self.auto_discover_sensitive_terms(canaries=canaries, custom_terms=custom_terms)
        counter = 1

        for term in terms:
            if "PROJECT" in term or "CUSTOMER" in term:
                pseudonym = f"customer_{chr(64 + counter)}" if counter <= 26 else f"customer_{counter}"
            elif "CANARY" in term:
                pseudonym = f"canary_token_{counter}"
            else:
                pseudonym = f"symbol_{counter}"

            counter += 1
            self.sanitize_identifier(term, pseudonym)

        self.mapping_store.save(capsule_hash=capsule_hash)
        return self.mapping_store
