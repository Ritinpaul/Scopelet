"""
Git repository history leak scanner.
Verifies that .git repositories, packfiles, commit history and git credentials are not bundled into capsules.
"""

from __future__ import annotations

from pathlib import Path
from typing import List
from ..models import SecretFinding


class GitScanner:
    """
    Scans a directory tree or file list to detect accidental inclusion of git history.
    """

    def scan_directory(self, target_dir: Path) -> List[SecretFinding]:
        """
        Inspects directory tree for .git folders, commit histories, packfiles, or git config files.
        """
        findings: List[SecretFinding] = []
        root = target_dir.resolve()

        for item in root.rglob("*"):
            rel_parts = item.relative_to(root).parts
            if ".git" in rel_parts:
                findings.append(
                    SecretFinding(
                        file_path=item.relative_to(root).as_posix(),
                        line_number=1,
                        category="git_leak",
                        description="Git repository history or object bundled in capsule",
                        matched_text=item.relative_to(root).as_posix(),
                        severity="CRITICAL",
                    )
                )
            elif item.is_file() and item.name in (".gitmodules", ".gitconfig", ".git-credentials"):
                findings.append(
                    SecretFinding(
                        file_path=item.relative_to(root).as_posix(),
                        line_number=1,
                        category="git_leak",
                        description="Git configuration file bundled in capsule",
                        matched_text=item.name,
                        severity="HIGH",
                    )
                )

        return findings
