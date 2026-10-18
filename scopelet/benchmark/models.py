"""
Benchmark data models and metrics tracking for Scopelet minimization evaluations.
Captures reduction ratios, evaluation counts, timing and verification outcomes.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def count_loc_in_files(base_dir: Path, file_paths: List[str]) -> int:
    """
    Computes total lines of code across specified relative file paths.
    Empty lines and comments are included for standard physical LOC measurement.
    """
    total_lines = 0
    for rel_path in file_paths:
        target = base_dir / rel_path
        if target.exists() and target.is_file():
            try:
                content = target.read_text(encoding="utf-8", errors="ignore")
                total_lines += len(content.splitlines())
            except Exception:
                continue
    return total_lines


@dataclass
class BenchmarkResult:
    """
    Performance and reduction metrics for a single bug or fixture evaluation.
    """
    bug_id: str
    fixture_name: str
    original_files: int
    original_loc: int
    capsule_files: int
    capsule_loc: int
    reduction_pct: float
    reducer_evaluations: int
    generation_time_s: float
    failure_preserved: bool
    reintegration_success: bool
    hidden_tests_passed: bool
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkSuite:
    """
    Aggregated benchmark suite containing results across multiple test cases.
    Computes summary statistics and exports structured markdown tables.
    """
    suite_name: str
    results: List[BenchmarkResult] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def add_result(self, result: BenchmarkResult) -> None:
        self.results.append(result)

    @property
    def total_cases(self) -> int:
        return len(self.results)

    @property
    def mean_reduction_pct(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.reduction_pct for r in self.results) / len(self.results)

    @property
    def mean_generation_time_s(self) -> float:
        if not self.results:
            return 0.0
        return sum(r.generation_time_s for r in self.results) / len(self.results)

    @property
    def total_reducer_evaluations(self) -> int:
        return sum(r.reducer_evaluations for r in self.results)

    @property
    def reintegration_rate(self) -> float:
        if not self.results:
            return 0.0
        successful = sum(1 for r in self.results if r.reintegration_success)
        return (successful / len(self.results)) * 100.0

    @property
    def hidden_pass_rate(self) -> float:
        if not self.results:
            return 0.0
        passed = sum(1 for r in self.results if r.hidden_tests_passed)
        return (passed / len(self.results)) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_name": self.suite_name,
            "created_at": self.created_at,
            "total_cases": self.total_cases,
            "mean_reduction_pct": round(self.mean_reduction_pct, 2),
            "mean_generation_time_s": round(self.mean_generation_time_s, 2),
            "total_reducer_evaluations": self.total_reducer_evaluations,
            "reintegration_rate": round(self.reintegration_rate, 2),
            "hidden_pass_rate": round(self.hidden_pass_rate, 2),
            "results": [r.to_dict() for r in self.results],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    def to_markdown_table(self) -> str:
        """
        Generates a GitHub-flavored Markdown table summarizing all benchmark results.
        """
        headers = [
            "Bug ID",
            "Fixture",
            "Orig Files",
            "Orig LOC",
            "Capsule Files",
            "Capsule LOC",
            "Reduction %",
            "Evals",
            "Time (s)",
            "Failure Kept",
            "Reintegrated",
            "Hidden Passed",
        ]
        divider = ["---"] * len(headers)

        rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(divider) + " |"]

        for r in self.results:
            row_items = [
                r.bug_id,
                r.fixture_name,
                str(r.original_files),
                str(r.original_loc),
                str(r.capsule_files),
                str(r.capsule_loc),
                f"{r.reduction_pct:.1f}%",
                str(r.reducer_evaluations),
                f"{r.generation_time_s:.2f}",
                "Yes" if r.failure_preserved else "No",
                "Yes" if r.reintegration_success else "No",
                "Yes" if r.hidden_tests_passed else "No",
            ]
            rows.append("| " + " | ".join(row_items) + " |")

        summary_block = (
            f"\n\n**Summary:**\n"
            f"- Total Test Cases: {self.total_cases}\n"
            f"- Mean LOC Reduction: {self.mean_reduction_pct:.1f}%\n"
            f"- Mean Generation Time: {self.mean_generation_time_s:.2f}s\n"
            f"- Reintegration Success Rate: {self.reintegration_rate:.1f}%\n"
            f"- Hidden Verification Pass Rate: {self.hidden_pass_rate:.1f}%\n"
        )

        return "\n".join(rows) + summary_block
