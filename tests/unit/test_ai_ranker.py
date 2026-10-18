"""
Unit tests for AI Relevance Ranker (Phase 6).
Validates LLM ranking, graceful fallback degradation and reducer prioritization.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from scopelet.ai import (
    AIRelevanceRanker,
    FileRanking,
    RankerResponse,
    RankingEvaluationMetrics,
)
from scopelet.reducer import (
    CandidateState,
    DeltaDebuggingReducer,
    OracleVerdict,
    ReducerOracle,
)


def test_ai_ranker_successful_response():
    mock_llm_output = json.dumps({
        "rankings": [
            {
                "file": "src/date/timezone.ts",
                "relevance": 0.95,
                "reason": "Direct defect location",
            },
            {
                "file": "src/customer/customer.repository.ts",
                "relevance": 0.15,
                "reason": "Unrelated module",
            },
        ]
    })

    ranker = AIRelevanceRanker(model="mock-llama")
    with patch.object(ranker, "_query_endpoint", return_value=mock_llm_output):
        response = ranker.rank_files(
            candidate_files=["src/date/timezone.ts", "src/customer/customer.repository.ts"],
            failure_summary="AssertionError: Expected 2026-10-18, Received 2026-10-17",
        )

    assert isinstance(response, RankerResponse)
    assert response.fallback_used is False
    assert len(response.rankings) == 2
    r_map = {r.file: r.relevance for r in response.rankings}
    assert r_map["src/date/timezone.ts"] == 0.95
    assert r_map["src/customer/customer.repository.ts"] == 0.15


def test_ai_ranker_relevance_scores_strictly_bounded():
    # LLM returns out-of-bound numbers (-0.5 and 1.8)
    mock_llm_output = json.dumps({
        "rankings": [
            {"file": "a.ts", "relevance": -0.5, "reason": "negative"},
            {"file": "b.ts", "relevance": 1.8, "reason": "overflow"},
        ]
    })

    ranker = AIRelevanceRanker()
    with patch.object(ranker, "_query_endpoint", return_value=mock_llm_output):
        response = ranker.rank_files(["a.ts", "b.ts"], failure_summary="Error")

    assert response.rankings[0].relevance == 0.0
    assert response.rankings[1].relevance == 1.0


def test_ai_ranker_graceful_degradation_when_offline():
    """
    When the local Ollama daemon is offline or connection times out,
    the ranker must degrade gracefully and never throw an unhandled exception.
    """
    ranker = AIRelevanceRanker(endpoint_url="http://127.0.0.1:99999/api/generate", timeout_seconds=0.1)
    response = ranker.rank_files(
        candidate_files=["src/date.ts", "src/utils.ts"],
        failure_summary="Test failed",
        stack_frames=["src/date.ts:12:5"],
    )

    assert isinstance(response, RankerResponse)
    assert response.fallback_used is True
    assert len(response.rankings) == 2
    # File in stack frame gets higher score
    r_map = {r.file: r.relevance for r in response.rankings}
    assert r_map["src/date.ts"] > r_map["src/utils.ts"]


def test_ai_ranker_benchmark_metrics():
    rankings = [
        FileRanking(file="src/bug.ts", relevance=0.9, reason="bug"),
        FileRanking(file="src/util.ts", relevance=0.3, reason="util"),
        FileRanking(file="src/extra.ts", relevance=0.2, reason="extra"),
    ]

    metrics = AIRelevanceRanker.compute_benchmark_metrics(
        rankings=rankings,
        ground_truth_relevant={"src/bug.ts"},
        k=2,
    )

    assert isinstance(metrics, RankingEvaluationMetrics)
    assert metrics.relevant_file_recall == 1.0
    assert metrics.initial_candidate_count == 3
    assert metrics.evaluations_saved >= 1


def test_ai_ranker_integration_with_reducer():
    """
    Tests that DeltaDebuggingReducer utilizes AI rankings to prioritize
    removing low-relevance files first.
    """
    mock_ranker = MagicMock()
    mock_ranker.rank_files.return_value = RankerResponse(
        rankings=[
            FileRanking(file="keep_me.ts", relevance=0.95, reason="needed"),
            FileRanking(file="remove_me_first.ts", relevance=0.10, reason="unrelated"),
            FileRanking(file="remove_me_second.ts", relevance=0.30, reason="support"),
        ],
        model="mock-model",
        latency_ms=10,
        fallback_used=False,
    )

    candidate = CandidateState(
        root_dir=Path("/dummy"),
        active_files={"keep_me.ts", "remove_me_first.ts", "remove_me_second.ts"},
        essential_files={"keep_me.ts"},
    )

    mock_oracle = MagicMock()
    mock_oracle.total_evaluations = 0
    mock_oracle.cache = None

    # Track sequence of files tested for removal
    tested_sequence = []

    def mock_evaluate(state):
        mock_oracle.total_evaluations += 1
        removed = set(candidate.active_files) - set(state.active_files)
        if removed:
            tested_sequence.append(list(removed)[0])
        return MagicMock(verdict=OracleVerdict.MATCH)

    mock_oracle.evaluate.side_effect = mock_evaluate

    reducer = DeltaDebuggingReducer(
        oracle=mock_oracle,
        ai_ranker=mock_ranker,
        failure_summary="Bug report",
    )

    reduced_state, result = reducer.reduce(candidate)

    # Low relevance file (0.10) must be tested before moderate relevance file (0.30)
    assert tested_sequence[0] == "remove_me_first.ts"
    assert tested_sequence[1] == "remove_me_second.ts"
    assert "keep_me.ts" in reduced_state.active_files
