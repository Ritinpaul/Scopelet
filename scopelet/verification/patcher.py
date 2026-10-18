"""
Unified diff parser and patch application engine.
Extracts target files from patches and applies unified diffs cleanly to workspaces.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple


class PatchError(Exception):
    """Raised when patch parsing or application fails."""
    pass


class PatchApplier:
    """
    Parses and applies unified diff patches with zero external tool dependencies.
    """

    DIFF_HEADER_RE = re.compile(r"^(?:---|\+\+\+)\s+(?:[ab]/)?(.+?)(?:\t.*|\s+\d{4}-\d{2}-\d{2}.*)?$")
    HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

    @classmethod
    def extract_modified_files(cls, patch_content: str) -> List[str]:
        """
        Extracts all normalized relative file paths touched by a unified diff.
        """
        modified: set[str] = set()
        lines = patch_content.splitlines()

        for line in lines:
            if line.startswith("+++ "):
                target = line[4:].strip()
                if target.startswith("b/"):
                    target = target[2:]
                target = target.split("\t")[0].strip()
                if target and target != "/dev/null":
                    modified.add(Path(target).as_posix())
            elif line.startswith("--- "):
                target = line[4:].strip()
                if target.startswith("a/"):
                    target = target[2:]
                target = target.split("\t")[0].strip()
                if target and target != "/dev/null":
                    modified.add(Path(target).as_posix())

        return sorted(modified)

    @classmethod
    def apply_patch(cls, patch_content: str, target_dir: Path) -> List[str]:
        """
        Applies a unified diff patch to target_dir and returns the list of modified files.
        """
        target = target_dir.resolve()
        if not target.exists():
            raise FileNotFoundError(f"Target directory does not exist: {target}")

        file_diffs = cls._split_file_diffs(patch_content)
        modified_paths: List[str] = []

        for old_path, new_path, hunk_lines in file_diffs:
            if new_path == "/dev/null":
                # File deletion
                del_file = target / old_path
                if del_file.exists():
                    del_file.unlink()
                modified_paths.append(old_path)
            elif old_path == "/dev/null":
                # New file creation
                dest_file = target / new_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                new_content = cls._apply_hunks([], hunk_lines, new_path)
                dest_file.write_text("".join(new_content), encoding="utf-8")
                modified_paths.append(new_path)
            else:
                # File modification
                dest_file = target / new_path
                if not dest_file.exists():
                    raise PatchError(f"Target file to patch not found: {dest_file}")

                original_content = dest_file.read_text(encoding="utf-8", errors="replace")
                orig_lines = original_content.splitlines(keepends=True)

                new_lines = cls._apply_hunks(orig_lines, hunk_lines, new_path)
                dest_file.write_text("".join(new_lines), encoding="utf-8")
                modified_paths.append(new_path)

        return sorted(set(modified_paths))

    @classmethod
    def _split_file_diffs(cls, patch_content: str) -> List[Tuple[str, str, List[str]]]:
        """
        Splits patch content into per-file chunks: (old_path, new_path, hunk_lines).
        """
        lines = patch_content.splitlines(keepends=True)
        file_diffs: List[Tuple[str, str, List[str]]] = []

        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            if line.startswith("--- "):
                old_path = cls._clean_path(line[4:].strip())
                i += 1
                if i < n and lines[i].startswith("+++ "):
                    new_path = cls._clean_path(lines[i][4:].strip())
                    i += 1

                    # Collect hunk lines until next file diff
                    hunk_lines: List[str] = []
                    while i < n and not lines[i].startswith("--- ") and not lines[i].startswith("diff --git"):
                        hunk_lines.append(lines[i])
                        i += 1

                    file_diffs.append((old_path, new_path, hunk_lines))
                    continue
            i += 1

        return file_diffs

    @classmethod
    def _clean_path(cls, path_str: str) -> str:
        s = path_str.split("\t")[0].strip()
        if s.startswith("a/") or s.startswith("b/"):
            s = s[2:]
        return s

    @classmethod
    def _apply_hunks(cls, orig_lines: List[str], hunk_lines: List[str], filename: str) -> List[str]:
        """
        Applies unified diff hunks sequentially to an array of original lines.
        """
        result: List[str] = []
        orig_idx = 0

        # Group hunk lines into individual hunks
        hunk_blocks: List[Tuple[int, int, int, int, List[str]]] = []
        curr_hunk: Optional[Tuple[int, int, int, int, List[str]]] = None

        for line in hunk_lines:
            match = cls.HUNK_HEADER_RE.match(line)
            if match:
                if curr_hunk:
                    hunk_blocks.append(curr_hunk)
                old_start = int(match.group(1))
                old_len = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_len = int(match.group(4)) if match.group(4) else 1
                curr_hunk = (old_start, old_len, new_start, new_len, [])
            elif curr_hunk is not None:
                curr_hunk[4].append(line)

        if curr_hunk:
            hunk_blocks.append(curr_hunk)

        if not hunk_blocks and not orig_lines:
            # File creation with no hunks
            return []

        for old_start, old_len, new_start, new_len, body in hunk_blocks:
            # 1-based line indexing
            target_start_idx = max(0, old_start - 1)

            # Copy unchanged lines preceding this hunk
            while orig_idx < target_start_idx and orig_idx < len(orig_lines):
                result.append(orig_lines[orig_idx])
                orig_idx += 1

            for hline in body:
                if not hline:
                    continue
                tag = hline[0]
                text = hline[1:]

                if tag == " ":
                    # Context line
                    if orig_idx < len(orig_lines):
                        result.append(orig_lines[orig_idx])
                        orig_idx += 1
                    else:
                        result.append(text)
                elif tag == "-":
                    # Removed line
                    orig_idx += 1
                elif tag == "+":
                    # Added line
                    result.append(text)
                elif tag == "\\":
                    # e.g., \ No newline at end of file
                    pass

        # Copy any remaining trailing lines
        while orig_idx < len(orig_lines):
            result.append(orig_lines[orig_idx])
            orig_idx += 1

        return result
