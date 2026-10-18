"""
Unit tests for Phase 24 AI ablation study metrics, comparisons and markdown summaries.
"""

import json
from pathlib import Path
import pytest

from scopelet.benchmark.ablation import (
    AblationComparison,
    AblationMetrics,
    AblationStudyRunner,
    AblationStudySuite,
)


def test_ablation_metrics_to_dict():
    """Validates serialization of AblationMetrics to dictionary."""
    m = AblationMetrics(
        candidate_files=15,
        reducer_evaluations=20,
        generation_time_s=6.5,
        final_loc=180,
        final_files=4,
        cache_hits=5,
    )
    d = m.to_dict()
    assert d["candidate_files"] == 15
    assert d["reducer_evaluations"] == 20
    assert d["generation_time_s"] == 6.5
    assert d["final_loc"] == 180


def test_ablation_comparison_savings_calculations():
    """Validates computation of evaluations saved, speedup and LOC parity."""
    with_ai = AblationMetrics(
        candidate_files=20,
        reducer_evaluations=12,
        generation_time_s=4.0,
        final_loc=150,
        final_files=3,
        cache_hits=4,
    )
    without_ai = AblationMetrics(
        candidate_files=20,
        reducer_evaluations=24,
        generation_time_s=8.0,
        final_loc=150,
        final_files=3,
        cache_hits=2,
    )

    comp = AblationComparison(
        case_id="CASE-01",
        with_ai=with_ai,
        without_ai=without_ai,
    )

    assert comp.evaluations_saved == 12  # 24 - 12
    assert comp.evaluations_saved_pct == 50.0  # 12 / 24 * 100
    assert comp.time_saved_s == 4.0  # 8.0 - 4.0
    assert comp.speedup_factor == 2.0  # 8.0 / 4.0
    assert comp.loc_parity is True


def test_ablation_study_suite_aggregations():
    """Validates summary statistics across multiple ablation comparisons."""
    c1 = AblationComparison(
        case_id="CASE-01",
        with_ai=AblationMetrics(10, 10, 2.0, 100, 2, 1),
        without_ai=AblationMetrics(10, 20, 4.0, 100, 2, 1),
    )
    c2 = AblationComparison(
        case_id="CASE-02",
        with_ai=AblationMetrics(15, 15, 3.0, 200, 3, 2),
        without_ai=AblationMetrics(15, 25, 6.0, 200, 3, 1),
    )

    suite = AblationStudySuite(suite_name="Ablation Benchmark")
    suite.add_comparison(c1)
    suite.add_comparison(c2)

    assert suite.total_cases == 2
    assert suite.mean_evaluations_saved == 10.0  # (10 + 10) / 2
    assert suite.mean_time_saved_s == 2.5  # ((4-2) + (6-3)) / 2 = (2 + 3) / 2 = 2.5
    assert suite.mean_speedup == 2.0  # (2.0 + 2.0) / 2
    assert suite.loc_parity_rate == 100.0


def test_ablation_study_suite_markdown_table():
    """Validates markdown table formatting for ablation comparison results."""
    c = AblationComparison(
        case_id="CASE-TIMEZONE",
        with_ai=AblationMetrics(12, 14, 5.0, 85, 2, 3),
        without_ai=AblationMetrics(12, 28, 10.0, 85, 2, 1),
    )
    suite = AblationStudySuite(suite_name="Format Suite")
    suite.add_comparison(c)

    md = suite.to_markdown_table()
    assert "| Case ID | Cand Files |" in md
    assert "| CASE-TIMEZONE | 12 | 14 | 28 | +14 | 50.0% |" in md
    assert "Speedup" in md
    assert "**Ablation Summary:**" in md
    assert "Mean Evaluations Saved: +14.0 (50.0%)" in md


def test_ablation_study_suite_json():
    """Validates JSON export of ablation suite."""
    c = AblationComparison(
        case_id="CASE-ROUND",
        with_ai=AblationMetrics(8, 6, 2.0, 50, 2, 1),
        without_ai=AblationMetrics(8, 12, 4.0, 50, 2, 1),
    )
    suite = AblationStudySuite(suite_name="JSON Suite")
    suite.add_comparison(c)

    data = json.loads(suite.to_json())
    assert data["suite_name"] == "JSON Suite"
    assert data["total_cases"] == 1
    assert data["mean_speedup"] == 2.0


def test_ablation_study_runner_mock(monkeypatch):
    """Validates that AblationStudyRunner executes dual-path minimization comparison."""
    runner = AblationStudyRunner()

    mock_metrics_ai = AblationMetrics(
        candidate_files=10,
        reducer_evaluations=8,
        generation_time_s=2.5,
        final_loc=100,
        final_files=2,
        cache_hits=3,
    )
    mock_metrics_no_ai = AblationMetrics(
        candidate_files=10,
        reducer_evaluations=16,
        generation_time_s=5.0,
        final_loc=100,
        final_files=2,
        cache_hits=1,
    )

    call_count = 0

    def mock_single_path(**kwargs):
        nonlocal call_count
        call_count += 1
        if kwargs.get("ai_ranker") is not None:
            return mock_metrics_ai
        return mock_metrics_no_ai

    monkeypatch.setattr(runner, "_run_single_path", mock_single_path)

    comp = runner.run_case(
        case_id="TEST-MOCK",
        fixture_dir=Path("fixtures/timezone-bug"),
        test_cmd="npm test",
    )

    assert call_count == 2
    assert comp.evaluations_saved == 8
    assert comp.speedup_factor == 2.0
    assert comp.loc_parity is True
