"""
Unit tests for Phase 25 Fine-tuned CapsuleRanker and training dataset synthesis.
"""

from pathlib import Path
import pytest

from scopelet.ai.capsule_ranker import (
    DatasetBuilder,
    FineTunedCapsuleRanker,
    RankingSample,
    evaluate_ranker_performance,
)


def test_ranking_sample_to_training_prompt():
    """Validates prompt generation for LLM fine-tuning from a RankingSample."""
    sample = RankingSample(
        bug_report="Invoice date offset by 1 day in Asia/Kolkata timezone",
        stack_trace="at formatToTimezoneDate (src/date/timezone.ts:18:22)",
        execution_graph={"src/date/timezone.ts": ["src/date/constants.ts"]},
        candidate_symbol="src/date/timezone.ts",
        relevant=True,
    )
    prompt = sample.to_training_prompt()
    assert "Bug: Invoice date offset" in prompt
    assert "Symbol: src/date/timezone.ts" in prompt
    assert "Dependencies: src/date/constants.ts" in prompt
    assert "Relevant: yes" in prompt


def test_dataset_builder_from_trace_and_patch():
    """Validates that DatasetBuilder labels candidates against known modified patch files."""
    candidates = ["src/date/timezone.ts", "src/utils/math.ts", "src/auth/jwt.ts"]
    modified = {"src/date/timezone.ts"}

    samples = DatasetBuilder.from_trace_and_patch(
        bug_report="Timezone bug",
        stack_trace="Error at timezone.ts",
        execution_graph={"src/date/timezone.ts": []},
        candidate_files=candidates,
        modified_files=modified,
    )

    assert len(samples) == 3
    sample_map = {s.candidate_symbol: s.relevant for s in samples}
    assert sample_map["src/date/timezone.ts"] is True
    assert sample_map["src/utils/math.ts"] is False
    assert sample_map["src/auth/jwt.ts"] is False


def test_dataset_builder_jsonl_roundtrip(tmp_path):
    """Validates exporting and loading fine-tuning datasets via JSON Lines."""
    samples = [
        RankingSample(
            bug_report="Bug A",
            stack_trace="Stack A",
            execution_graph={},
            candidate_symbol="src/a.ts",
            relevant=True,
        ),
        RankingSample(
            bug_report="Bug B",
            stack_trace="Stack B",
            execution_graph={},
            candidate_symbol="src/b.ts",
            relevant=False,
        ),
    ]

    out_file = tmp_path / "dataset.jsonl"
    DatasetBuilder.export_jsonl(samples, out_file)
    assert out_file.exists()

    loaded = DatasetBuilder.load_jsonl(out_file)
    assert len(loaded) == 2
    assert loaded[0].candidate_symbol == "src/a.ts"
    assert loaded[0].relevant is True
    assert loaded[1].candidate_symbol == "src/b.ts"
    assert loaded[1].relevant is False


def test_fine_tuned_ranker_scores_stack_frame_highest():
    """Validates that symbols present in the stack trace receive elevated relevance."""
    ranker = FineTunedCapsuleRanker()
    stack_trace = "Error in src/services/invoice.ts line 42\nat calculateTotal"

    score_stack_file = ranker.score_symbol(
        symbol="src/services/invoice.ts",
        bug_report="Invoice total calculation error",
        stack_trace=stack_trace,
    )
    score_unrelated = ranker.score_symbol(
        symbol="src/auth/login.ts",
        bug_report="Invoice total calculation error",
        stack_trace=stack_trace,
    )

    assert score_stack_file > score_unrelated
    assert score_stack_file >= 0.70
    assert score_unrelated <= 0.30


def test_fine_tuned_ranker_ranks_files_order():
    """Validates that rank_files returns rankings sorted by relevance descending."""
    ranker = FineTunedCapsuleRanker()
    candidates = ["src/unrelated.ts", "src/target.ts", "src/helper.ts"]
    stack_frames = ["src/target.ts:15"]

    resp = ranker.rank_files(
        candidate_files=candidates,
        failure_summary="Target failure occurred",
        stack_frames=stack_frames,
    )

    assert resp.model == "scopelet-capsule-ranker-v1"
    assert len(resp.rankings) == 3
    # First ranked file must be the stack frame target
    assert resp.rankings[0].file == "src/target.ts"
    assert resp.rankings[0].relevance > resp.rankings[1].relevance


def test_evaluate_ranker_performance_metrics():
    """Validates precision, recall and F1 calculation against labeled samples."""
    ranker = FineTunedCapsuleRanker()
    samples = [
        RankingSample(
            bug_report="Error in calc",
            stack_trace="calc.ts",
            execution_graph={},
            candidate_symbol="calc.ts",
            relevant=True,
        ),
        RankingSample(
            bug_report="Error in calc",
            stack_trace="calc.ts",
            execution_graph={},
            candidate_symbol="other.ts",
            relevant=False,
        ),
    ]

    metrics = evaluate_ranker_performance(ranker, samples, threshold=0.5)
    assert metrics.total_samples == 2
    assert metrics.true_positives == 1
    assert metrics.true_negatives == 1
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1_score == 1.0
