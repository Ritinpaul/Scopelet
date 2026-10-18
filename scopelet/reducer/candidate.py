"""
Candidate repository state representation for delta-debugging reduction.
Tracks active files, modified contents, and provides deterministic hashing and materialization.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Set

DEFAULT_IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".scopelet",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
    ".vitest",
}

DEFAULT_ESSENTIAL_FILES = {
    "package.json",
    "tsconfig.json",
    "vitest.config.ts",
    "vitest.config.js",
    "vitest.config.mjs",
    "vitest.config.cjs",
}

LOCKFILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
}


def link_directory(source: Path, target: Path) -> None:
    """
    Creates a junction (on Windows) or symlink (on POSIX) linking target to source.
    Avoids copying large directories like node_modules.
    """
    if target.exists() or target.is_symlink():
        return

    target.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(str(source.resolve()), str(target.resolve()))
            return
        except Exception:
            pass

    try:
        os.symlink(source.resolve(), target.resolve(), target_is_directory=True)
    except Exception:
        # Fallback to copy if linking fails or unsupported
        shutil.copytree(source, target, dirs_exist_ok=True)


class CandidateState:
    """
    Immutable-style representation of a candidate repository state during minimization.
    """

    def __init__(
        self,
        root_dir: Path,
        active_files: Set[str],
        modified_contents: Optional[Dict[str, str]] = None,
        essential_files: Optional[Set[str]] = None,
    ):
        self.root_dir = root_dir.resolve()
        self.active_files: Set[str] = set(active_files)
        self.modified_contents: Dict[str, str] = modified_contents or {}
        self.essential_files: Set[str] = set(essential_files or DEFAULT_ESSENTIAL_FILES)

    @classmethod
    def from_directory(
        cls,
        root_dir: Path,
        ignore_dirs: Optional[Set[str]] = None,
        essential_files: Optional[Set[str]] = None,
    ) -> CandidateState:
        """
        Discovers all files in root_dir, excluding ignored directories.
        """
        root = root_dir.resolve()
        ignored = ignore_dirs or DEFAULT_IGNORE_DIRS
        active: Set[str] = set()

        for p in root.rglob("*"):
            if p.is_file():
                rel_parts = p.relative_to(root).parts
                if any(part in ignored for part in rel_parts):
                    continue
                active.add(p.relative_to(root).as_posix())

        return cls(
            root_dir=root,
            active_files=active,
            essential_files=essential_files,
        )

    def file_count(self) -> int:
        """Returns total active files count."""
        return len(self.active_files)

    def get_content(self, rel_path: str) -> str:
        """
        Retrieves the content of an active file, using modified_contents if present,
        otherwise reading from root_dir.
        """
        normalized = Path(rel_path).as_posix()
        if normalized in self.modified_contents:
            return self.modified_contents[normalized]

        src_path = self.root_dir / normalized
        if src_path.is_file():
            try:
                return src_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return ""
        return ""

    def loc(self) -> int:
        """
        Calculates total non-empty lines of code across all active files.
        Excludes auto-generated lockfiles.
        """
        total = 0
        for rel_path in self.active_files:
            file_name = Path(rel_path).name
            if file_name in LOCKFILE_NAMES or rel_path in LOCKFILE_NAMES:
                continue
            content = self.get_content(rel_path)
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            total += len(lines)
        return total

    def compute_tree_hash(self) -> str:
        """
        Computes deterministic SHA-256 hash over sorted active files and their contents.
        """
        hasher = hashlib.sha256()
        for rel_path in sorted(self.active_files):
            hasher.update(rel_path.encode("utf-8"))
            content = self.get_content(rel_path)
            hasher.update(content.encode("utf-8"))
        return hasher.hexdigest()

    def prune_file(self, rel_path: str) -> CandidateState:
        """
        Returns a new CandidateState with rel_path removed from active_files.
        """
        normalized = Path(rel_path).as_posix()
        new_active = self.active_files - {normalized}
        new_mods = {k: v for k, v in self.modified_contents.items() if k != normalized}
        return CandidateState(
            root_dir=self.root_dir,
            active_files=new_active,
            modified_contents=new_mods,
            essential_files=self.essential_files,
        )

    def prune_files(self, paths: Iterable[str]) -> CandidateState:
        """
        Returns a new CandidateState with multiple paths removed.
        """
        norm_paths = {Path(p).as_posix() for p in paths}
        new_active = self.active_files - norm_paths
        new_mods = {k: v for k, v in self.modified_contents.items() if k not in norm_paths}
        return CandidateState(
            root_dir=self.root_dir,
            active_files=new_active,
            modified_contents=new_mods,
            essential_files=self.essential_files,
        )

    def with_content(self, rel_path: str, new_content: str) -> CandidateState:
        """
        Returns a new CandidateState with modified content for a specific file.
        """
        normalized = Path(rel_path).as_posix()
        new_active = self.active_files | {normalized}
        new_mods = dict(self.modified_contents)
        new_mods[normalized] = new_content
        return CandidateState(
            root_dir=self.root_dir,
            active_files=new_active,
            modified_contents=new_mods,
            essential_files=self.essential_files,
        )

    def materialize(self, target_dir: Path, link_node_modules: bool = True) -> None:
        """
        Synchronizes target_dir to mirror this candidate state.
        Removes files no longer active and writes active files.
        """
        target = target_dir.resolve()
        target.mkdir(parents=True, exist_ok=True)

        if link_node_modules:
            src_nm = self.root_dir / "node_modules"
            tgt_nm = target / "node_modules"
            if src_nm.exists() and not tgt_nm.exists() and not tgt_nm.is_symlink():
                link_directory(src_nm, tgt_nm)

        # Remove files in target that are not in active_files
        for existing in target.rglob("*"):
            if existing.is_file():
                rel = existing.relative_to(target).as_posix()
                if rel.startswith("node_modules/") or rel.startswith(".scopelet/"):
                    continue
                if rel not in self.active_files:
                    try:
                        existing.unlink()
                    except OSError:
                        pass

        # Write or update active files
        for rel_path in self.active_files:
            dest_file = target / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            content = self.get_content(rel_path)

            needs_write = True
            if dest_file.exists():
                try:
                    if dest_file.read_text(encoding="utf-8", errors="replace") == content:
                        needs_write = False
                except Exception:
                    pass

            if needs_write:
                dest_file.write_text(content, encoding="utf-8")
