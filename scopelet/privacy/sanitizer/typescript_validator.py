"""
TypeScript and JavaScript validator confirming type-safety and syntactic validity after renames.
Runs `tsc --noEmit` if available and performs Tree-sitter syntax validation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import tree_sitter
import tree_sitter_typescript

IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".scopelet",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
}


class TypeScriptValidator:
    """
    Validates that code changes maintain syntax correctness and TypeScript type compliance.
    """

    def __init__(self):
        self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
        self.tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
        self.ts_parser = tree_sitter.Parser(self.ts_lang)
        self.tsx_parser = tree_sitter.Parser(self.tsx_lang)

    def validate_syntax(self, workspace_dir: Path) -> Tuple[bool, Optional[str]]:
        """
        Parses all TypeScript and JavaScript files with Tree-sitter to ensure no syntax errors exist.
        """
        root = workspace_dir.resolve()
        for item in sorted(root.rglob("*")):
            if not item.is_file():
                continue

            rel_parts = item.relative_to(root).parts
            if any(part in IGNORE_DIRS for part in rel_parts):
                continue

            if item.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
                try:
                    code_bytes = item.read_bytes()
                except (OSError, PermissionError):
                    continue

                parser = self.tsx_parser if item.suffix in (".tsx", ".jsx") else self.ts_parser
                tree = parser.parse(code_bytes)
                if tree.root_node.has_error:
                    rel_path = item.relative_to(root).as_posix()
                    return False, f"Syntax error detected in {rel_path} after AST transformation"

        return True, None

    def find_tsc_executable(self, workspace_dir: Path) -> Optional[Path]:
        """
        Locates a local or global tsc executable.
        """
        root = workspace_dir.resolve()
        # 1. Local workspace node_modules/.bin
        is_win = os.name == "nt"
        candidate_bin = "tsc.cmd" if is_win else "tsc"
        local_tsc = root / "node_modules" / ".bin" / candidate_bin
        if local_tsc.exists():
            return local_tsc

        # 2. Local typescript package runner
        local_ts_js = root / "node_modules" / "typescript" / "bin" / "tsc"
        if local_ts_js.exists():
            return local_ts_js

        # 3. Global tsc in PATH
        global_tsc = shutil.which("tsc")
        if global_tsc:
            return Path(global_tsc)

        return None

    def validate_types(self, workspace_dir: Path, timeout: int = 30) -> Tuple[bool, Optional[str]]:
        """
        Executes `tsc --noEmit` if a tsconfig.json and tsc compiler are present.
        """
        root = workspace_dir.resolve()
        tsconfig = root / "tsconfig.json"
        if not tsconfig.exists():
            # If no tsconfig.json, skip type check and rely on syntax validation
            return True, None

        tsc_exec = self.find_tsc_executable(root)
        if not tsc_exec:
            return True, None

        cmd = [str(tsc_exec), "--noEmit"]
        if tsc_exec.suffix == ".js" or not os.access(str(tsc_exec), os.X_OK):
            node_exec = shutil.which("node") or "node"
            cmd = [node_exec, str(tsc_exec), "--noEmit"]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode != 0:
                err_out = (proc.stdout + "\n" + proc.stderr).strip()
                return False, f"TypeScript compiler (tsc) validation failed:\n{err_out[:500]}"
            return True, None
        except (subprocess.TimeoutExpired, OSError) as e:
            return False, f"TypeScript compiler execution error: {e}"

    def validate(self, workspace_dir: Path) -> Tuple[bool, Optional[str]]:
        """
        Runs full validation: Tree-sitter syntax validation followed by TypeScript type check.
        """
        syntax_ok, syntax_err = self.validate_syntax(workspace_dir)
        if not syntax_ok:
            return False, syntax_err

        types_ok, types_err = self.validate_types(workspace_dir)
        if not types_ok:
            return False, types_err

        return True, None
