"""
Unit tests for the Tree-sitter static analysis engine, symbol extractor,
and directed repository dependency graph.
"""

from pathlib import Path
import pytest
from scopelet.analysis.static.node import GraphNode
from scopelet.analysis.static.graph import DependencyGraph
from scopelet.analysis.static.ts_analyzer import TypeScriptAnalyzer

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_graph_node_initialization():
    node = GraphNode(
        symbol="calculateTax",
        file="src/billing/tax.ts",
        type="function",
        loc=25,
    )
    assert node.symbol == "calculateTax"
    assert node.file == "src/billing/tax.ts"
    assert node.type == "function"
    assert node.loc == 25
    assert node.imports == []
    assert node.imported_by == []


def test_dependency_graph_edge_addition():
    g = DependencyGraph()
    n1 = GraphNode(symbol="A", file="a.ts")
    n2 = GraphNode(symbol="B", file="b.ts")
    g.add_node(n1)
    g.add_node(n2)
    g.add_edge("a.ts", "b.ts")

    assert "b.ts" in g.get_dependencies("a.ts")
    assert "a.ts" in g.get_dependents("b.ts")
    assert "b.ts" in g.nodes["a.ts"].imports
    assert "a.ts" in g.nodes["b.ts"].imported_by


def test_reachability_linear_chain():
    g = DependencyGraph()
    g.add_edge("test.ts", "service.ts")
    g.add_edge("service.ts", "util.ts")
    g.add_edge("service.ts", "model.ts")
    g.add_edge("unrelated.ts", "other.ts")

    reachable = g.reachable(["test.ts"])
    assert reachable == {"test.ts", "service.ts", "util.ts", "model.ts"}
    assert "unrelated.ts" not in reachable
    assert "other.ts" not in reachable


def test_reachability_diamond_graph():
    g = DependencyGraph()
    g.add_edge("root.ts", "left.ts")
    g.add_edge("root.ts", "right.ts")
    g.add_edge("left.ts", "leaf.ts")
    g.add_edge("right.ts", "leaf.ts")

    reachable = g.reachable(["root.ts"])
    assert reachable == {"root.ts", "left.ts", "right.ts", "leaf.ts"}


def test_reachability_cyclic_graph():
    g = DependencyGraph()
    g.add_edge("a.ts", "b.ts")
    g.add_edge("b.ts", "c.ts")
    g.add_edge("c.ts", "a.ts")  # cycle
    g.add_edge("c.ts", "d.ts")

    reachable = g.reachable(["a.ts"])
    assert reachable == {"a.ts", "b.ts", "c.ts", "d.ts"}


def test_mermaid_export():
    g = DependencyGraph()
    g.add_edge("src/a.ts", "src/b.ts")
    mermaid = g.to_mermaid(["src/a.ts"])
    assert "flowchart TD" in mermaid
    assert 'src_a_ts["src/a.ts"] --> src_b_ts["src/b.ts"]' in mermaid


def test_analyzer_parses_named_imports(tmp_path):
    code = """
    import { DateService, formatHelper } from '../date/date.service.js';
    import { Invoice } from './invoice.model.js';
    export const x = 1;
    """
    f = tmp_path / "test.ts"
    f.write_text(code, encoding="utf-8")

    analyzer = TypeScriptAnalyzer()
    imports, _ = analyzer.extract_imports_and_symbols(f)
    assert len(imports) == 2
    specifiers = [imp[0] for imp in imports]
    assert "../date/date.service.js" in specifiers
    assert "./invoice.model.js" in specifiers

    named_symbols = imports[0][1]
    assert "DateService" in named_symbols
    assert "formatHelper" in named_symbols


def test_analyzer_parses_classes_and_functions(tmp_path):
    code = """
    export class InvoiceService {
        constructor() {}
    }
    export function calculateTotal(items: any[]): number {
        return 100;
    }
    export interface Item { id: string; }
    """
    f = tmp_path / "sample.ts"
    f.write_text(code, encoding="utf-8")

    analyzer = TypeScriptAnalyzer()
    _, symbols = analyzer.extract_imports_and_symbols(f)
    sym_dict = {s["name"]: s["type"] for s in symbols}

    assert "InvoiceService" in sym_dict
    assert sym_dict["InvoiceService"] == "class"
    assert "calculateTotal" in sym_dict
    assert sym_dict["calculateTotal"] == "function"
    assert "Item" in sym_dict
    assert sym_dict["Item"] == "interface"


def test_resolve_import_handles_js_to_ts(tmp_path):
    src = tmp_path / "src"
    date_dir = src / "date"
    date_dir.mkdir(parents=True)
    target_ts = date_dir / "date.service.ts"
    target_ts.write_text("export class DateService {}", encoding="utf-8")

    inv_dir = src / "invoice"
    inv_dir.mkdir(parents=True)
    inv_file = inv_dir / "invoice.service.ts"
    inv_file.write_text("import { DateService } from '../date/date.service.js';", encoding="utf-8")

    analyzer = TypeScriptAnalyzer()
    resolved = analyzer.resolve_import_path(inv_file, "../date/date.service.js", tmp_path)
    assert resolved == "src/date/date.service.ts"


def test_resolve_import_handles_index_files(tmp_path):
    src = tmp_path / "src"
    utils_dir = src / "utils"
    utils_dir.mkdir(parents=True)
    (utils_dir / "index.ts").write_text("export const util = true;", encoding="utf-8")

    caller = src / "app.ts"
    caller.write_text("import { util } from './utils';", encoding="utf-8")

    analyzer = TypeScriptAnalyzer()
    resolved = analyzer.resolve_import_path(caller, "./utils", tmp_path)
    assert resolved == "src/utils/index.ts"


def test_resolve_import_ignores_third_party_modules(tmp_path):
    f = tmp_path / "src" / "test.ts"
    f.parent.mkdir(parents=True)
    f.write_text("import { describe } from 'vitest';", encoding="utf-8")

    analyzer = TypeScriptAnalyzer()
    resolved = analyzer.resolve_import_path(f, "vitest", tmp_path)
    assert resolved is None


# --- Golden Fixture A Reachability Tests ---

def test_fixture_a_reachability_contains_defect_chain():
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_a)

    entry = "tests/invoice-timezone.test.ts"
    reachable = graph.reachable([entry])

    # Core defect chain must be reachable
    assert "tests/invoice-timezone.test.ts" in reachable
    assert "src/invoice/invoice.service.ts" in reachable
    assert "src/date/date.service.ts" in reachable
    assert "src/date/date.formatter.ts" in reachable
    assert "src/date/timezone.ts" in reachable
    assert "src/date/date.constants.ts" in reachable


def test_fixture_a_reachability_excludes_unrelated_modules():
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_a)

    entry = "tests/invoice-timezone.test.ts"
    reachable = graph.reachable([entry])

    # Unrelated domains must be excluded from this bug's slice!
    assert "src/analytics/analytics.service.ts" not in reachable
    assert "src/analytics/tracker.service.ts" not in reachable
    assert "src/admin/admin.controller.ts" not in reachable
    assert "src/admin/audit.service.ts" not in reachable
    assert "src/notifications/sms.service.ts" not in reachable
    assert "src/notifications/webhook.service.ts" not in reachable
    assert "src/auth/auth.service.ts" not in reachable
    assert "src/auth/jwt.service.ts" not in reachable
    assert "src/customer/customer.repository.ts" not in reachable


# --- Golden Fixture B Reachability Tests ---

def test_fixture_b_reachability_contains_pricing_chain():
    fixture_b = ROOT_DIR / "fixtures" / "rounding-bug"
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_b)

    entry = "tests/rounding.test.ts"
    reachable = graph.reachable([entry])

    # Core chain must be reachable
    assert "tests/rounding.test.ts" in reachable
    assert "src/pricing/pricing.service.ts" in reachable
    assert "src/utils/math.utils.ts" in reachable

    # Unrelated domains must be excluded
    assert "src/catalog/product.repository.ts" not in reachable
    assert "src/shipping/shipping.service.ts" not in reachable


# --- Golden Fixture C Reachability Tests ---

def test_fixture_c_reachability_contains_profile_cache():
    fixture_c = ROOT_DIR / "fixtures" / "cache-bug"
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_c)

    entry = "tests/cache.test.ts"
    reachable = graph.reachable([entry])

    assert "tests/cache.test.ts" in reachable
    assert "src/profile/profile.service.ts" in reachable
    assert "src/cache/cache.service.ts" in reachable
    assert "src/repository/user.repository.ts" in reachable

    # Controller is not called directly by unit test
    assert "src/profile/profile.controller.ts" not in reachable
