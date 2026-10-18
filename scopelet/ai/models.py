"""
Data models for AI-driven relevance ranking (Phase 6).
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class FileRanking(BaseModel):
    """
    Relevance ranking score and rationale for an individual candidate file.
    """
    file: str = Field(..., description="Relative path of the candidate file")
    relevance: float = Field(..., ge=0.0, le=1.0, description="Relevance score between 0.0 and 1.0")
    reason: str = Field(..., description="Rationale for the assigned relevance score")


class RankerResponse(BaseModel):
    """
    Structured outcome of AI relevance ranking evaluation.
    """
    rankings: List[FileRanking] = Field(default_factory=list, description="List of file rankings")
    model: str = Field(..., description="Identifier of the model used")
    latency_ms: int = Field(default=0, description="Execution latency in milliseconds")
    fallback_used: bool = Field(default=False, description="Whether fallback degradation was activated")


class RankingEvaluationMetrics(BaseModel):
    """
    Benchmark metrics tracking ranking quality and reduction efficiency gains.
    """
    relevant_file_recall: float = Field(default=1.0, description="Fraction of essential files captured in top k")
    initial_candidate_count: int = Field(default=0, description="Total candidate files evaluated")
    evaluations_saved: int = Field(default=0, description="Reducer execution runs saved through prioritization")
