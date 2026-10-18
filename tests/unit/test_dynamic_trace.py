"""
Unit tests for the dynamic execution tracer, V8 coverage parser and candidate slice merger.
"""

from pathlib import Path
import pytest
import json
import tempfile

from scopelet.analysis.dynamic import (
    DynamicTracer,
    DynamicTraceResult,
    normalize_v8_url,
    parse_v8_coverage_dir,
    compute_candidate_slice,
)
from scopelet.analysis.static import TypeScriptAnalyzer, DependencyGraph

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def test_normalize_v8_url_valid(tmp_path):
    repo_file = tmp_path / "src" / "service.ts"
    repo_file.parent.mkdir(parents=True)
    repo_file.write_text("export const a = 1;", encoding="utf-8")

    url = repo_file.resolve().as_uri()
    rel = normalize_v8_url(url, tmp_path)
    assert rel == "src/service.ts"


def test_normalize_v8_url_ignores_node_modules(tmp_path):
    nm_file = tmp_path / "node_modules" / "vitest" / "index.js"
    nm_file.parent.mkdir(parents=True)
    nm_file.write_text("module.exports = {};", encoding="utf-8")

    url = nm_file.resolve().as_uri()
    rel = normalize_v8_url(url, tmp_path)
    assert rel is None


def test_normalize_v8_url_ignores_external_files(tmp_path):
    external_file = tmp_path.parent / "external.js"
    external_file.write_text("console.log(1)", encoding="utf-8")

    url = external_file.resolve().as_uri()
    rel = normalize_v8_url(url, tmp_path)
    assert rel is None


def test_normalize_v8_url_ignores_non_file_schemes(tmp_path):
    assert normalize_v8_url("node:internal/process/task_queues", tmp_path) is None
    assert normalize_v8_url("http://localhost:3000/app.js", tmp_path) is None
    assert normalize_v8_url("", tmp_path) is None


def test_parse_v8_coverage_dir_empty_or_missing(tmp_path):
    res = parse_v8_coverage_dir(tmp_path / "nonexistent", tmp_path)
    assert res.executed_files == set()
    assert res.total_coverage_files_inspected == 0


def test_parse_v8_coverage_mock_json(tmp_path):
    src_file = tmp_path / "src" / "math.ts"
    src_file.parent.mkdir(parents=True)
    src_file.write_text("export function add(a, b) { return a + b; }", encoding="utf-8")

    cov_dir = tmp_path / "cov"
    cov_dir.mkdir()

    cov_payload = {
        "result": [
            {
                "scriptId": "42",
                "url": src_file.resolve().as_uri(),
                "functions": [
                    {
                        "functionName": "add",
                        "ranges": [{"startOffset": 0, "endOffset": 45, "count": 2}],
                        "isBlockCoverage": True,
                    }
                ],
            }
        ]
    }
    (cov_dir / "coverage-1.json").write_text(json.dumps(cov_payload), encoding="utf-8")

    res = parse_v8_coverage_dir(cov_dir, tmp_path)
    assert "src/math.ts" in res.executed_files
    assert res.total_coverage_files_inspected == 1
    assert "src/math.ts" in res.file_details
    assert len(res.file_details["src/math.ts"].functions) == 1
    assert res.file_details["src/math.ts"].functions[0].name == "add"


def test_fixture_a_dynamic_trace_records_defect_chain():
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    tracer = DynamicTracer(default_timeout=60)
    report = tracer.trace("npm test -- invoice-timezone", cwd=fixture_a)

    executed = report.trace.executed_files

    # Core defect chain must be in dynamic trace
    assert "src/date/timezone.ts" in executed
    assert "src/date/date.service.ts" in executed
    assert "src/date/date.formatter.ts" in executed
    assert "src/date/date.constants.ts" in executed
    assert "src/invoice/invoice.service.ts" in executed
    assert "src/invoice/invoice.calculator.ts" in executed

    # Unexecuted modules must be excluded
    assert "src/customer/customer.repository.ts" not in executed
    assert "src/admin/admin.controller.ts" not in executed
    assert "src/analytics/analytics.service.ts" not in executed
    assert "src/auth/auth.service.ts" not in executed


def test_fixture_b_dynamic_trace_records_pricing_chain():
    fixture_b = ROOT_DIR / "fixtures" / "rounding-bug"
    tracer = DynamicTracer(default_timeout=60)
    report = tracer.trace("npm test -- rounding", cwd=fixture_b)

    executed = report.trace.executed_files

    # Executed pricing service and math utils
    assert "src/pricing/pricing.service.ts" in executed
    assert "src/utils/math.utils.ts" in executed
    assert "tests/rounding.test.ts" in executed

    # Unexecuted catalog repository must be excluded
    assert "src/catalog/product.repository.ts" not in executed
    assert "src/shipping/shipping.service.ts" not in executed


def test_fixture_c_dynamic_trace_records_cache_chain():
    fixture_c = ROOT_DIR / "fixtures" / "cache-bug"
    tracer = DynamicTracer(default_timeout=60)
    report = tracer.trace("npm test -- cache", cwd=fixture_c)

    executed = report.trace.executed_files

    assert "src/profile/profile.service.ts" in executed
    assert "src/cache/cache.service.ts" in executed
    assert "src/repository/user.repository.ts" in executed
    assert "tests/cache.test.ts" in executed

    # Controller is not called directly by unit test
    assert "src/profile/profile.controller.ts" not in executed


def test_compute_candidate_slice_fixture_a():
    fixture_a = ROOT_DIR / "fixtures" / "timezone-bug"
    analyzer = TypeScriptAnalyzer()
    graph = analyzer.build_graph(fixture_a)

    tracer = DynamicTracer(default_timeout=60)
    report = tracer.trace("npm test -- invoice-timezone", cwd=fixture_a)

    stack_frames = ["tests/invoice-timezone.test.ts", "src/date/timezone.ts"]
    candidate_slice = compute_candidate_slice(
        static_graph=graph,
        dynamic_trace=report.trace,
        stack_frames=stack_frames,
        all_files=set(graph.nodes.keys()),
    )

    # Core defect files must be present
    assert "src/date/timezone.ts" in candidate_slice.combined_slice
    assert "src/date/date.service.ts" in candidate_slice.combined_slice
    assert "src/invoice/invoice.service.ts" in candidate_slice.combined_slice

    # Type-only interface directly imported by invoice.service is preserved
    assert "src/invoice/invoice.model.ts" in candidate_slice.combined_slice

    # Unrelated files must be pruned
    assert "src/customer/customer.repository.ts" not in candidate_slice.combined_slice
    assert "src/admin/admin.controller.ts" not in candidate_slice.combined_slice
    assert "src/analytics/analytics.service.ts" not in candidate_slice.combined_slice

    # High reduction achieved (>80% pruned)
    assert candidate_slice.reduction_percentage > 80.0
    assert len(candidate_slice.combined_slice) < 15
    assert candidate_slice.total_files_count >= 60


def test_candidate_slice_preserves_stack_frames_unconditionally():
    graph = DependencyGraph()
    graph.add_edge("entry.ts", "service.ts")
    graph.add_edge("service.ts", "dep.ts")

    dynamic_trace = {"service.ts"}
    stack_frames = ["untraced_error.ts"]
    all_files = {"entry.ts", "service.ts", "dep.ts", "untraced_error.ts", "other.ts"}

    cand = compute_candidate_slice(
        static_graph=graph,
        dynamic_trace=dynamic_trace,
        stack_frames=stack_frames,
        all_files=all_files,
    )

    assert "untraced_error.ts" in cand.combined_slice
    assert "service.ts" in cand.combined_slice
    assert "other.ts" not in cand.combined_slice
