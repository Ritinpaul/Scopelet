"""
AI Ablation study engine for Scopelet.
Compares minimization performance and evaluation counts with and without AI ranking.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import count_loc_in_files
from ..ai.ranker import AIRelevanceRanker
from ..capture.runner import capture
from ..reducer import CandidateState, DeltaDebuggingReducer, ReducerOracle, ReducerProgress


@dataclass
class AblationMetrics:
    """
    Minimization telemetry for a specific ranker configuration.
    """
    candidate_files: int
    reducer_evaluations: int
    generation_time_s: float
    final_loc: int
    final_files: int
    cache_hits: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AblationComparison:
    """
    Side-by-side comparison of reducer performance with vs without AI ranking.
    """
    case_id: str
    with_ai: AblationMetrics
    without_ai: AblationMetrics
    notes: Optional[str] = None

    @property
    def evaluations_saved(self) -> int:
        return self.without_ai.reducer_evaluations - self.with_ai.reducer_evaluations

    @property
    def evaluations_saved_pct(self) -> float:
        if self.without_ai.reducer_evaluations <= 0:
            return 0.0
        return (self.evaluations_saved / self.without_ai.reducer_evaluations) * 100.0

    @property
    def time_saved_s(self) -> float:
        return self.without_ai.generation_time_s - self.with_ai.generation_time_s

    @property
    def speedup_factor(self) -> float:
        if self.with_ai.generation_time_s <= 0:
            return 1.0
        return self.without_ai.generation_time_s / self.with_ai.generation_time_s

    @property
    def loc_parity(self) -> bool:
        return self.with_ai.final_loc == self.without_ai.final_loc

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "evaluations_saved": self.evaluations_saved,
            "evaluations_saved_pct": round(self.evaluations_saved_pct, 2),
            "time_saved_s": round(self.time_saved_s, 2),
            "speedup_factor": round(self.speedup_factor, 2),
            "loc_parity": self.loc_parity,
            "with_ai": self.with_ai.to_dict(),
            "without_ai": self.without_ai.to_dict(),
            "notes": self.notes,
        }


@dataclass
class AblationStudySuite:
    """
    Aggregates ablation comparisons across multiple test cases.
    """
    suite_name: str
    comparisons: List[AblationComparison] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_comparison(self, comp: AblationComparison) -> None:
        self.comparisons.append(comp)

    @property
    def total_cases(self) -> int:
        return len(self.comparisons)

    @property
    def mean_evaluations_saved(self) -> float:
        if not self.comparisons:
            return 0.0
        return sum(c.evaluations_saved for c in self.comparisons) / len(self.comparisons)

    @property
    def mean_evaluations_saved_pct(self) -> float:
        if not self.comparisons:
            return 0.0
        return sum(c.evaluations_saved_pct for c in self.comparisons) / len(self.comparisons)

    @property
    def mean_time_saved_s(self) -> float:
        if not self.comparisons:
            return 0.0
        return sum(c.time_saved_s for c in self.comparisons) / len(self.comparisons)

    @property
    def mean_speedup(self) -> float:
        if not self.comparisons:
            return 1.0
        return sum(c.speedup_factor for c in self.comparisons) / len(self.comparisons)

    @property
    def loc_parity_rate(self) -> float:
        if not self.comparisons:
            return 0.0
        parity_count = sum(1 for c in self.comparisons if c.loc_parity)
        return (parity_count / len(self.comparisons)) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "created_at": self.created_at,
            "total_cases": self.total_cases,
            "mean_evaluations_saved": round(self.mean_evaluations_saved, 2),
            "mean_evaluations_saved_pct": round(self.mean_evaluations_saved_pct, 2),
            "mean_time_saved_s": round(self.mean_time_saved_s, 2),
            "mean_speedup": round(self.mean_speedup, 2),
            "loc_parity_rate": round(self.loc_parity_rate, 2),
            "comparisons": [c.to_dict() for c in self.comparisons],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_markdown_table(self) -> str:
        """
        Renders a Markdown comparison table with summary metrics.
        """
        headers = [
            "Case ID",
            "Cand Files",
            "With AI Evals",
            "W/O AI Evals",
            "Evals Saved",
            "Evals Saved %",
            "With AI Time",
            "W/O AI Time",
            "Speedup",
            "LOC Parity",
        ]
        divider = ["---"] * len(headers)
        rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(divider) + " |"]

        for c in self.comparisons:
            row = [
                c.case_id,
                str(c.with_ai.candidate_files),
                str(c.with_ai.reducer_evaluations),
                str(c.without_ai.reducer_evaluations),
                f"{c.evaluations_saved:+d}",
                f"{c.evaluations_saved_pct:.1f}%",
                f"{c.with_ai.generation_time_s:.2f}s",
                f"{c.without_ai.generation_time_s:.2f}s",
                f"{c.speedup_factor:.2f}x",
                "Yes" if c.loc_parity else "No",
            ]
            rows.append("| " + " | ".join(row) + " |")

        summary = (
            f"\n\n**Ablation Summary:**\n"
            f"- Total Comparisons: {self.total_cases}\n"
            f"- Mean Evaluations Saved: {self.mean_evaluations_saved:+.1f} ({self.mean_evaluations_saved_pct:.1f}%)\n"
            f"- Mean Time Saved: {self.mean_time_saved_s:+.2f}s\n"
            f"- Mean Speedup: {self.mean_speedup:.2f}x\n"
            f"- Final LOC Parity Rate: {self.loc_parity_rate:.1f}%\n"
        )
        return "\n".join(rows) + summary


class AblationStudyRunner:
    """
    Runs dual-path minimization comparing DDmin with vs without AI ranker.
    """

    def __init__(self, ranker: Optional[Any] = None):
        self.ranker = ranker or AIRelevanceRanker(enable_fallback=True)

    def run_case(
        self,
        case_id: str,
        fixture_dir: Path,
        test_cmd: str = "npm test",
        candidate_slice_files: Optional[List[str]] = None,
        max_evaluations: int = 50,
    ) -> AblationComparison:
        """
        Executes minimization twice: with AI ranking and without AI ranking.
        """
        fixture = fixture_dir.resolve()

        # Capture target failure fingerprint
        cap_result = capture(command=test_cmd, cwd=fixture)
        target_fp = cap_result.failure.fingerprint
        stack_frames = cap_result.failure.frames

        initial_state = CandidateState.from_directory(fixture)
        slice_set = set(candidate_slice_files) if candidate_slice_files else None

        # Path 1: With AI ranking
        metrics_with_ai = self._run_single_path(
            fixture=fixture,
            test_cmd=test_cmd,
            target_fp=target_fp,
            stack_frames=stack_frames,
            initial_state=initial_state,
            slice_set=slice_set,
            ai_ranker=self.ranker,
            max_evaluations=max_evaluations,
        )

        # Path 2: Without AI ranking (baseline)
        metrics_without_ai = self._run_single_path(
            fixture=fixture,
            test_cmd=test_cmd,
            target_fp=target_fp,
            stack_frames=stack_frames,
            initial_state=initial_state,
            slice_set=slice_set,
            ai_ranker=None,
            max_evaluations=max_evaluations,
        )

        return AblationComparison(
            case_id=case_id,
            with_ai=metrics_with_ai,
            without_ai=metrics_without_ai,
        )

    def _run_single_path(
        self,
        fixture: Path,
        test_cmd: str,
        target_fp: str,
        stack_frames: List[str],
        initial_state: CandidateState,
        slice_set: Optional[set],
        ai_ranker: Optional[Any],
        max_evaluations: int,
    ) -> AblationMetrics:
        temp_dir = Path(tempfile.mkdtemp(prefix="scopelet_ablation_ws_"))
        start_time = time.perf_counter()
        try:
            oracle = ReducerOracle(
                command=test_cmd,
                expected_fingerprint=target_fp,
                workspace_dir=temp_dir,
            )
            reducer = DeltaDebuggingReducer(
                oracle=oracle,
                progress=ReducerProgress(quiet=True),
                protected_files=set(stack_frames),
                max_evaluations=max_evaluations,
                ai_ranker=ai_ranker,
                failure_summary="Test defect failure",
                stack_frames=stack_frames,
            )
            reduced_state, stats = reducer.reduce(
                initial_state=initial_state,
                candidate_slice_files=slice_set,
            )
            duration_s = time.perf_counter() - start_time
            active_files_list = sorted(list(reduced_state.active_files))
            final_loc = count_loc_in_files(fixture, active_files_list)

            return AblationMetrics(
                candidate_files=len(initial_state.active_files),
                reducer_evaluations=stats.total_evaluations,
                generation_time_s=round(duration_s, 2),
                final_loc=final_loc,
                final_files=len(active_files_list),
                cache_hits=stats.cache_hits,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
