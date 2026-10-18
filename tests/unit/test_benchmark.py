"""
Unit tests for benchmark telemetry models, LOC computation, metric aggregations and runner.
Validates Phase 23 requirements.
"""

import json
from pathlib import Path
import pytest

from scopelet.benchmark.models import (
    BenchmarkResult,
    BenchmarkSuite,
    count_loc_in_files,
)
from scopelet.benchmark.runner import BenchmarkRunner


def test_count_loc_in_files(tmp_path):
    """Validates that line-of-code counting correctly sums lines across multiple files."""
    f1 = tmp_path / "a.ts"
    f1.write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    f2 = tmp_path / "b.ts"
    f2.write_text("const x = 10;\nconst y = 20;\n", encoding="utf-8")

    loc = count_loc_in_files(tmp_path, ["a.ts", "b.ts"])
    assert loc == 5


def test_benchmark_result_to_dict():
    """Validates serialization of BenchmarkResult to dictionary."""
    res = BenchmarkResult(
        bug_id="BUG-001",
        fixture_name="timezone-bug",
        original_files=10,
        original_loc=500,
        capsule_files=3,
        capsule_loc=150,
        reduction_pct=70.0,
        reducer_evaluations=12,
        generation_time_s=4.5,
        failure_preserved=True,
        reintegration_success=True,
        hidden_tests_passed=True,
    )
    d = res.to_dict()
    assert d["bug_id"] == "BUG-001"
    assert d["reduction_pct"] == 70.0
    assert d["hidden_tests_passed"] is True


def test_benchmark_suite_aggregations():
    """Validates that summary statistics across multiple results are computed correctly."""
    r1 = BenchmarkResult(
        bug_id="BUG-001",
        fixture_name="fixture-1",
        original_files=20,
        original_loc=1000,
        capsule_files=4,
        capsule_loc=200,
        reduction_pct=80.0,
        reducer_evaluations=15,
        generation_time_s=10.0,
        failure_preserved=True,
        reintegration_success=True,
        hidden_tests_passed=True,
    )
    r2 = BenchmarkResult(
        bug_id="BUG-002",
        fixture_name="fixture-2",
        original_files=10,
        original_loc=500,
        capsule_files=4,
        capsule_loc=200,
        reduction_pct=60.0,
        reducer_evaluations=25,
        generation_time_s=20.0,
        failure_preserved=True,
        reintegration_success=True,
        hidden_tests_passed=False,
    )

    suite = BenchmarkSuite(suite_name="Test Suite")
    suite.add_result(r1)
    suite.add_result(r2)

    assert suite.total_cases == 2
    assert suite.mean_reduction_pct == 70.0  # (80 + 60) / 2
    assert suite.mean_generation_time_s == 15.0  # (10 + 20) / 2
    assert suite.total_reducer_evaluations == 40  # 15 + 25
    assert suite.reintegration_rate == 100.0  # 2 of 2
    assert suite.hidden_pass_rate == 50.0  # 1 of 2


def test_benchmark_suite_markdown_table():
    """Validates that markdown table output contains table structure and summary metrics."""
    suite = BenchmarkSuite(suite_name="Formatting Suite")
    suite.add_result(
        BenchmarkResult(
            bug_id="BUG-TZ",
            fixture_name="timezone-bug",
            original_files=12,
            original_loc=450,
            capsule_files=3,
            capsule_loc=90,
            reduction_pct=80.0,
            reducer_evaluations=14,
            generation_time_s=5.2,
            failure_preserved=True,
            reintegration_success=True,
            hidden_tests_passed=True,
        )
    )

    md = suite.to_markdown_table()
    assert "| Bug ID | Fixture |" in md
    assert "| BUG-TZ | timezone-bug |" in md
    assert "80.0%" in md
    assert "**Summary:**" in md
    assert "Mean LOC Reduction: 80.0%" in md


def test_benchmark_suite_json_export():
    """Validates that JSON export is valid and roundtrips with sorted keys."""
    suite = BenchmarkSuite(suite_name="JSON Suite")
    suite.add_result(
        BenchmarkResult(
            bug_id="BUG-ROUND",
            fixture_name="rounding-bug",
            original_files=8,
            original_loc=300,
            capsule_files=2,
            capsule_loc=60,
            reduction_pct=80.0,
            reducer_evaluations=8,
            generation_time_s=3.1,
            failure_preserved=True,
            reintegration_success=True,
            hidden_tests_passed=True,
        )
    )

    json_str = suite.to_json()
    data = json.loads(json_str)
    assert data["suite_name"] == "JSON Suite"
    assert data["total_cases"] == 1
    assert data["mean_reduction_pct"] == 80.0
    assert len(data["results"]) == 1


def test_benchmark_runner_suite_collection(monkeypatch):
    """Validates that BenchmarkRunner collects results into a BenchmarkSuite."""
    runner = BenchmarkRunner(suite_name="Mock Benchmark")

    dummy_result = BenchmarkResult(
        bug_id="MOCK-1",
        fixture_name="mock-fixture",
        original_files=5,
        original_loc=100,
        capsule_files=2,
        capsule_loc=30,
        reduction_pct=70.0,
        reducer_evaluations=5,
        generation_time_s=1.2,
        failure_preserved=True,
        reintegration_success=True,
        hidden_tests_passed=True,
    )
    monkeypatch.setattr(runner, "run_case", lambda **kw: dummy_result)

    suite = runner.run_suite([{"bug_id": "MOCK-1", "fixture_dir": Path(".")}])
    assert suite.total_cases == 1
    assert suite.results[0].bug_id == "MOCK-1"
    assert suite.mean_reduction_pct == 70.0

