"""
Isolated worktree manager for safe patch reintegration.
Creates isolated sandboxes via git worktree or file mirroring without modifying active branches.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from ..reducer.candidate import link_directory


class IsolatedWorktree:
    """
    Context manager managing a temporary git worktree or isolated file sandbox.
    """

    def __init__(self, repo_dir: Path, prefer_git_worktree: bool = True):
        self.repo_dir = repo_dir.resolve()
        self.prefer_git_worktree = prefer_git_worktree
        self.worktree_dir: Optional[Path] = None
        self._is_git_worktree = False

    def __enter__(self) -> Path:
        return self.create()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cleanup()

    def create(self) -> Path:
        """
        Creates an isolated worktree or copy-sandbox.
        """
        temp_dir = Path(tempfile.mkdtemp(prefix="scopelet_worktree_"))
        self.worktree_dir = temp_dir

        if self.prefer_git_worktree and (self.repo_dir / ".git").exists():
            try:
                # Attempt git worktree creation
                cmd = ["git", "worktree", "add", "--detach", str(temp_dir), "HEAD"]
                res = subprocess.run(
                    cmd,
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if res.returncode == 0:
                    self._is_git_worktree = True
                    # Link node_modules if present in original repo
                    orig_nm = self.repo_dir / "node_modules"
                    if orig_nm.exists() and not (temp_dir / "node_modules").exists():
                        link_directory(orig_nm, temp_dir / "node_modules")
                    return temp_dir
            except Exception:
                pass

        # Fallback to copy sandbox
        shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        for item in self.repo_dir.iterdir():
            name = item.name
            if name in (".git", ".scopelet", ".pytest_cache", "__pycache__", "node_modules"):
                continue

            dst = temp_dir / name
            if item.is_dir():
                shutil.copytree(item, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            else:
                shutil.copy2(item, dst)

        orig_nm = self.repo_dir / "node_modules"
        if orig_nm.exists() and orig_nm.is_dir():
            link_directory(orig_nm, temp_dir / "node_modules")

        self._is_git_worktree = False
        return temp_dir

    def cleanup(self) -> None:
        """
        Cleans up the worktree or sandbox directory.
        """
        if not self.worktree_dir or not self.worktree_dir.exists():
            return

        if self._is_git_worktree:
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(self.worktree_dir)],
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    timeout=30,
                )
            except Exception:
                pass

        shutil.rmtree(self.worktree_dir, ignore_errors=True)
        self.worktree_dir = None
