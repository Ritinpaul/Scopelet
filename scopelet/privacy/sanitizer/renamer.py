"""
Tree-sitter powered AST identifier and symbol renamer.
Performs semantic renaming across TypeScript and JavaScript source files without touching comments.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set, Tuple
import tree_sitter
import tree_sitter_typescript

IDENTIFIER_NODE_TYPES = {
    "identifier",
    "property_identifier",
    "type_identifier",
    "shorthand_property_identifier",
    "shorthand_property_identifier_pattern",
    "statement_identifier",
}

IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".scopelet",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
}


class ASTRenamer:
    """
    AST-based renamer for TypeScript and JavaScript code.
    Identifies exact identifier AST nodes and rewrites byte offsets deterministically.
    """

    def __init__(self):
        self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
        self.tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
        self.ts_parser = tree_sitter.Parser(self.ts_lang)
        self.tsx_parser = tree_sitter.Parser(self.tsx_lang)

    def _get_parser(self, file_path: Path) -> tree_sitter.Parser:
        if file_path.suffix in (".tsx", ".jsx"):
            return self.tsx_parser
        return self.ts_parser

    def find_replacement_ranges(
        self,
        code_bytes: bytes,
        target_name: str,
        is_tsx: bool = False,
        rename_strings: bool = False,
    ) -> List[Tuple[int, int]]:
        """
        Locates (start_byte, end_byte) ranges for target_name in the AST.
        Only matches exact identifier tokens or string fragments.
        """
        parser = self.tsx_parser if is_tsx else self.ts_parser
        tree = parser.parse(code_bytes)
        target_bytes = target_name.encode("utf-8")
        ranges: List[Tuple[int, int]] = []

        def visit(node: tree_sitter.Node) -> None:
            if node.type in IDENTIFIER_NODE_TYPES:
                if node.text == target_bytes:
                    ranges.append((node.start_byte, node.end_byte))
            elif rename_strings and node.type == "string_fragment":
                if node.text == target_bytes:
                    ranges.append((node.start_byte, node.end_byte))

            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return ranges

    def rename_in_bytes(
        self,
        code_bytes: bytes,
        old_name: str,
        new_name: str,
        is_tsx: bool = False,
        rename_strings: bool = False,
    ) -> Tuple[bytes, int]:
        """
        Applies AST rename on raw code bytes.
        Returns modified bytes and the count of replacements made.
        """
        ranges = self.find_replacement_ranges(
            code_bytes,
            old_name,
            is_tsx=is_tsx,
            rename_strings=rename_strings,
        )
        if not ranges:
            return code_bytes, 0

        # Deduplicate and sort descending by start_byte to keep earlier offsets stable
        unique_ranges = sorted(set(ranges), key=lambda r: r[0], reverse=True)
        new_bytes = new_name.encode("utf-8")
        result = code_bytes

        for start_byte, end_byte in unique_ranges:
            result = result[:start_byte] + new_bytes + result[end_byte:]

        return result, len(unique_ranges)

    def rename_file(
        self,
        file_path: Path,
        old_name: str,
        new_name: str,
        rename_strings: bool = False,
    ) -> int:
        """
        Renames all AST occurrences of old_name to new_name in a file.
        Returns the number of replacements.
        """
        target = file_path.resolve()
        if not target.is_file():
            return 0

        try:
            code_bytes = target.read_bytes()
        except (OSError, PermissionError):
            return 0

        is_tsx = target.suffix in (".tsx", ".jsx")
        modified_bytes, count = self.rename_in_bytes(
            code_bytes,
            old_name,
            new_name,
            is_tsx=is_tsx,
            rename_strings=rename_strings,
        )

        if count > 0:
            target.write_bytes(modified_bytes)

        return count

    def rename_directory(
        self,
        target_dir: Path,
        old_name: str,
        new_name: str,
        rename_strings: bool = False,
    ) -> Dict[str, int]:
        """
        Recursively scans and renames AST occurrences across all TypeScript and JavaScript files.
        Returns a dictionary mapping relative file paths to replacement counts.
        """
        root = target_dir.resolve()
        results: Dict[str, int] = {}

        for item in sorted(root.rglob("*")):
            if not item.is_file():
                continue

            rel_parts = item.relative_to(root).parts
            if any(part in IGNORE_DIRS for part in rel_parts):
                continue

            if item.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
                count = self.rename_file(item, old_name, new_name, rename_strings=rename_strings)
                if count > 0:
                    results[item.relative_to(root).as_posix()] = count

        return results
