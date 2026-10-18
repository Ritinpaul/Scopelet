"""
Reverse identifier mapping engine for patch reintegration.
Reverses privacy sanitization mappings to restore original proprietary identifiers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional


class ReverseIdentifierMapper:
    """
    Reverses privacy sanitization transformations on candidate patches.
    """

    def __init__(self, mapping: Optional[Dict[str, str]] = None):
        # mapping can be original -> sanitized or sanitized -> original
        self.mapping: Dict[str, str] = mapping or {}

    @classmethod
    def from_file(cls, mapping_file: Path) -> ReverseIdentifierMapper:
        """
        Loads mapping from a JSON file.
        Expects format: {"mapping": {"ORIG": "SANITIZED", ...}} or {"ORIG": "SANITIZED", ...}
        """
        path = mapping_file.resolve()
        if not path.exists():
            return cls({})

        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "mapping" in data and isinstance(data["mapping"], dict):
            raw_map = data["mapping"]
        elif isinstance(data, dict):
            raw_map = data
        else:
            raw_map = {}

        return cls(raw_map)

    def get_reverse_map(self) -> Dict[str, str]:
        """
        Returns sanitized -> original translation dictionary.
        """
        # If mapping is original -> sanitized, invert it
        # E.g. {"PROJECT_NEBULA": "customer_A"} -> {"customer_A": "PROJECT_NEBULA"}
        reverse_map: Dict[str, str] = {}
        for orig, sanitized in self.mapping.items():
            reverse_map[sanitized] = orig
        return reverse_map

    def un_sanitize_text(self, text: str) -> str:
        """
        Restores original identifiers in text using word boundary matching.
        Longer sanitized identifiers are matched first to prevent partial replacements.
        """
        rev_map = self.get_reverse_map()
        if not rev_map:
            return text

        # Sort keys by length descending
        sorted_keys = sorted(rev_map.keys(), key=len, reverse=True)

        # Regex matching word tokens or exact symbols
        pattern = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted_keys) + r")\b")

        def _replace(match: re.Match) -> str:
            val = match.group(0)
            return rev_map.get(val, val)

        return pattern.sub(_replace, text)

    def un_sanitize_patch(self, patch_content: str) -> str:
        """
        Un-sanitizes unified diff content line by line, preserving diff markers.
        """
        if not self.mapping:
            return patch_content

        lines = patch_content.splitlines(keepends=True)
        restored_lines = []

        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                # Do not corrupt file paths in header lines unless paths were sanitized
                restored_lines.append(self.un_sanitize_text(line))
            elif line.startswith("+") or line.startswith("-") or line.startswith(" "):
                # Diff payload or context line
                prefix = line[0]
                rest = line[1:]
                restored_lines.append(prefix + self.un_sanitize_text(rest))
            else:
                restored_lines.append(line)

        return "".join(restored_lines)
