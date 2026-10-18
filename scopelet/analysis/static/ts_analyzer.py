"""
Tree-sitter powered TypeScript and JavaScript static analysis and dependency extraction.
Resolves ESM/CJS import specifiers, symbol definitions, and builds repository dependency graphs.
"""

from pathlib import Path
from typing import List, Optional, Set, Dict, Tuple
import tree_sitter
import tree_sitter_typescript
from .node import GraphNode, SymbolType
from .graph import DependencyGraph

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


class TypeScriptAnalyzer:
    """
    Parses TypeScript/JavaScript ASTs using tree-sitter to build project dependency graphs.
    """

    def __init__(self):
        self.ts_lang = tree_sitter.Language(tree_sitter_typescript.language_typescript())
        self.tsx_lang = tree_sitter.Language(tree_sitter_typescript.language_tsx())
        self.ts_parser = tree_sitter.Parser(self.ts_lang)
        self.tsx_parser = tree_sitter.Parser(self.tsx_lang)

    def parse_code(self, code_bytes: bytes, is_tsx: bool = False) -> tree_sitter.Tree:
        """Parses source code bytes into a Tree-sitter AST."""
        parser = self.tsx_parser if is_tsx else self.ts_parser
        return parser.parse(code_bytes)

    def extract_imports_and_symbols(
        self,
        file_path: Path,
    ) -> Tuple[List[Tuple[str, List[str]]], List[Dict[str, str]]]:
        """
        Parses a single source file to extract:
        1. Imported module specifiers and named symbols: [(specifier, [symbols])]
        2. Defined symbols: [{'name': ..., 'type': ...}]
        """
        try:
            code = file_path.read_bytes()
        except (OSError, PermissionError):
            return [], []

        is_tsx = file_path.suffix in (".tsx", ".jsx")
        tree = self.parse_code(code, is_tsx=is_tsx)

        imports: List[Tuple[str, List[str]]] = []
        symbols: List[Dict[str, str]] = []

        root = tree.root_node
        for child in root.children:
            # 1. Import statements: import { a, b } from './module.js'
            if child.type == "import_statement":
                source_node = child.child_by_field_name("source")
                if source_node:
                    specifier = source_node.text.decode("utf-8").strip("'\"`")
                    named_symbols: List[str] = []
                    # Search for import_specifier
                    for sub in child.children:
                        if sub.type == "import_clause":
                            for clause_child in sub.children:
                                if clause_child.type == "named_imports":
                                    for spec in clause_child.children:
                                        if spec.type == "import_specifier":
                                            name_node = spec.child_by_field_name("name")
                                            if name_node:
                                                named_symbols.append(name_node.text.decode("utf-8"))
                    imports.append((specifier, named_symbols))

            # 2. Export statements: export class / function / const ...
            elif child.type == "export_statement":
                decl = child.child_by_field_name("declaration")
                if decl:
                    sym = self._extract_declaration_symbol(decl)
                    if sym:
                        symbols.append(sym)

            # 3. Top-level declarations
            elif child.type in ("function_declaration", "class_declaration", "lexical_declaration"):
                sym = self._extract_declaration_symbol(child)
                if sym:
                    symbols.append(sym)

        return imports, symbols

    def _extract_declaration_symbol(self, node: tree_sitter.Node) -> Optional[Dict[str, str]]:
        """Extracts symbol name and kind from a declaration node."""
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                return {"name": name_node.text.decode("utf-8"), "type": "function"}

        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                return {"name": name_node.text.decode("utf-8"), "type": "class"}

        elif node.type == "lexical_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        return {"name": name_node.text.decode("utf-8"), "type": "variable"}

        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                return {"name": name_node.text.decode("utf-8"), "type": "interface"}

        elif node.type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                return {"name": name_node.text.decode("utf-8"), "type": "type"}

        return None

    @staticmethod
    def resolve_import_path(
        from_file: Path,
        specifier: str,
        project_root: Path,
    ) -> Optional[str]:
        """
        Resolves a relative import specifier (e.g. '../date/date.service.js') to a
        normalized repository-relative path (e.g. 'src/date/date.service.ts').
        """
        if not (specifier.startswith("./") or specifier.startswith("../")):
            # Non-relative / third-party package
            return None

        from_dir = from_file.parent
        raw_target = (from_dir / specifier).resolve()

        # Potential extensions to check
        candidates = [
            raw_target,
            raw_target.with_suffix(".ts"),
            raw_target.with_suffix(".tsx"),
            raw_target.with_suffix(".js"),
            raw_target.with_suffix(".d.ts"),
            raw_target / "index.ts",
            raw_target / "index.tsx",
            raw_target / "index.js",
        ]

        # Handle ESM .js imports that map to .ts source files
        if specifier.endswith(".js"):
            no_ext = specifier[:-3]
            base_target = (from_dir / no_ext).resolve()
            candidates.insert(0, base_target.with_suffix(".ts"))
            candidates.insert(1, base_target.with_suffix(".tsx"))
            candidates.insert(2, base_target / "index.ts")

        for cand in candidates:
            if cand.exists() and cand.is_file():
                try:
                    rel = cand.relative_to(project_root.resolve()).as_posix()
                    return rel
                except ValueError:
                    pass

        return None

    def build_graph(self, project_root: Path) -> DependencyGraph:
        """
        Scans all TypeScript/JavaScript files in project_root and builds a DependencyGraph.
        """
        root = project_root.resolve()
        graph = DependencyGraph()

        all_ts_files: List[Path] = []
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
                rel_parts = p.relative_to(root).parts
                if any(ignored in rel_parts for ignored in IGNORE_DIRS):
                    continue
                all_ts_files.append(p)

        # 1. Create nodes for all discovered files
        for f in all_ts_files:
            rel_path = f.relative_to(root).as_posix()
            try:
                loc = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
            except Exception:
                loc = 0

            node = GraphNode(
                symbol=f.stem,
                file=rel_path,
                type="file",
                loc=loc,
            )
            graph.add_node(node)

        # 2. Extract imports and build edges
        for f in all_ts_files:
            src_rel = f.relative_to(root).as_posix()
            raw_imports, _ = self.extract_imports_and_symbols(f)

            for specifier, _ in raw_imports:
                resolved_dep = self.resolve_import_path(f, specifier, root)
                if resolved_dep and resolved_dep in graph.nodes:
                    graph.add_edge(src_rel, resolved_dep)

        return graph
