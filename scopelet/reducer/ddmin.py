"""
Hierarchical Delta-Debugging (ddmin) Reducer Engine.
Minimizes candidate repository states using hierarchical pruning (directories -> files -> AST).
Guarantees behavior preservation by gating every reduction against the oracle failure fingerprint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set
from pydantic import BaseModel, Field

from .candidate import CandidateState
from .oracle import ReducerOracle, OracleVerdict
from .progress import ReducerProgress


class ReductionResult(BaseModel):
    initial_files: int
    final_files: int
    initial_loc: int
    final_loc: int
    total_evaluations: int
    cache_hits: int
    kept_files: List[str]
    pruned_files: List[str]
    loc_reduction_percentage: float
    file_reduction_percentage: float


class DeltaDebuggingReducer:
    """
    Hierarchical delta-debugging minimization engine.
    """

    def __init__(
        self,
        oracle: ReducerOracle,
        progress: Optional[ReducerProgress] = None,
        protected_files: Optional[Set[str]] = None,
        max_evaluations: int = 500,
        ai_ranker: Optional[Any] = None,
        failure_summary: Optional[str] = None,
        stack_frames: Optional[List[str]] = None,
    ):
        self.oracle = oracle
        self.progress = progress or ReducerProgress(quiet=True)
        self.protected_files: Set[str] = {Path(p).as_posix() for p in (protected_files or set())}
        self.max_evaluations = max_evaluations
        self.ai_ranker = ai_ranker
        self.failure_summary = failure_summary
        self.stack_frames = stack_frames

    def reduce(
        self,
        initial_state: CandidateState,
        candidate_slice_files: Optional[Set[str]] = None,
    ) -> tuple[CandidateState, ReductionResult]:
        """
        Executes hierarchical minimization:
        1. Baseline verification
        2. Candidate slice bulk pre-pruning (if candidate_slice_files provided)
        3. Directory-level bulk pruning
        4. File-by-file delta debugging
        """
        initial_files_count = initial_state.file_count()
        initial_loc = initial_state.loc()

        self.progress.print_banner(
            repo_files=initial_files_count,
            candidate_files=len(candidate_slice_files) if candidate_slice_files else initial_files_count,
            initial_loc=initial_loc,
        )

        # Step 1: Baseline verification
        self.progress.on_phase_start("Phase 1: Baseline Verification", "Checking initial candidate state")
        baseline_result = self.oracle.evaluate(initial_state)
        if baseline_result.verdict != OracleVerdict.MATCH:
            raise ValueError(
                f"Initial repository state does not reproduce the expected failure fingerprint. "
                f"Verdict: {baseline_result.verdict.value}, error: {baseline_result.error_message}"
            )

        current_state = initial_state
        cache_hits = 0

        # Step 2: Slice bulk pre-pruning
        if candidate_slice_files is not None:
            norm_slice = {Path(p).as_posix() for p in candidate_slice_files}
            files_to_prune = (
                current_state.active_files - norm_slice - current_state.essential_files - self.protected_files
            )

            if files_to_prune:
                self.progress.on_phase_start(
                    "Phase 2: Candidate Slice Pre-Pruning",
                    f"Attempting bulk pruning of {len(files_to_prune)} unreached files",
                )
                trial_state = current_state.prune_files(files_to_prune)
                trial_result = self.oracle.evaluate(trial_state)
                if trial_result.cached:
                    cache_hits += 1

                self.progress.on_step(
                    target=f"Bulk slice pruning ({len(files_to_prune)} files)",
                    verdict=trial_result.verdict,
                    current_files=trial_state.file_count() if trial_result.verdict == OracleVerdict.MATCH else current_state.file_count(),
                    current_loc=trial_state.loc() if trial_result.verdict == OracleVerdict.MATCH else current_state.loc(),
                    initial_loc=initial_loc,
                    evaluations=self.oracle.total_evaluations,
                    cache_hits=self.oracle.cache.hits if self.oracle.cache else 0,
                )

                if trial_result.verdict == OracleVerdict.MATCH:
                    current_state = trial_state

        # Step 3: Directory-level bulk pruning
        self.progress.on_phase_start("Phase 3: Directory Bulk Pruning", "Testing removable subdirectories")
        dirs_to_test = self._extract_removable_directories(current_state)

        for dir_path in dirs_to_test:
            if self.oracle.total_evaluations >= self.max_evaluations:
                break

            dir_files = [
                f for f in current_state.active_files
                if f.startswith(dir_path + "/") and f not in current_state.essential_files and f not in self.protected_files
            ]

            if not dir_files:
                continue

            trial_state = current_state.prune_files(dir_files)
            trial_result = self.oracle.evaluate(trial_state)

            self.progress.on_step(
                target=f"Directory {dir_path}/ ({len(dir_files)} files)",
                verdict=trial_result.verdict,
                current_files=trial_state.file_count() if trial_result.verdict == OracleVerdict.MATCH else current_state.file_count(),
                current_loc=trial_state.loc() if trial_result.verdict == OracleVerdict.MATCH else current_state.loc(),
                initial_loc=initial_loc,
                evaluations=self.oracle.total_evaluations,
                cache_hits=self.oracle.cache.hits if self.oracle.cache else 0,
            )

            if trial_result.verdict == OracleVerdict.MATCH:
                current_state = trial_state

        # Step 4: File-by-file delta debugging
        self.progress.on_phase_start("Phase 4: File-by-File Minimization", "Testing individual file removals")
        removable_files = [
            f for f in current_state.active_files
            if f not in current_state.essential_files and f not in self.protected_files
        ]

        if self.ai_ranker and removable_files:
            summary = self.failure_summary or "Test failure"
            resp = self.ai_ranker.rank_files(removable_files, summary, stack_frames=self.stack_frames)
            scores = {r.file: r.relevance for r in resp.rankings}
            # Least relevant files first for removal
            removable_files.sort(key=lambda f: (scores.get(f, 0.5), f))
        else:
            removable_files.sort()

        for file_path in removable_files:
            if self.oracle.total_evaluations >= self.max_evaluations:
                break

            if file_path not in current_state.active_files:
                continue

            trial_state = current_state.prune_file(file_path)
            trial_result = self.oracle.evaluate(trial_state)

            self.progress.on_step(
                target=f"File {file_path}",
                verdict=trial_result.verdict,
                current_files=trial_state.file_count() if trial_result.verdict == OracleVerdict.MATCH else current_state.file_count(),
                current_loc=trial_state.loc() if trial_result.verdict == OracleVerdict.MATCH else current_state.loc(),
                initial_loc=initial_loc,
                evaluations=self.oracle.total_evaluations,
                cache_hits=self.oracle.cache.hits if self.oracle.cache else 0,
            )

            if trial_result.verdict == OracleVerdict.MATCH:
                current_state = trial_state

        final_files_count = current_state.file_count()
        final_loc = current_state.loc()
        total_evals = self.oracle.total_evaluations
        total_cache_hits = self.oracle.cache.hits if self.oracle.cache else 0

        kept_list = sorted(current_state.active_files)
        pruned_list = sorted(initial_state.active_files - current_state.active_files)

        loc_reduction = ((initial_loc - final_loc) / initial_loc * 100) if initial_loc > 0 else 0.0
        file_reduction = ((initial_files_count - final_files_count) / initial_files_count * 100) if initial_files_count > 0 else 0.0

        result = ReductionResult(
            initial_files=initial_files_count,
            final_files=final_files_count,
            initial_loc=initial_loc,
            final_loc=final_loc,
            total_evaluations=total_evals,
            cache_hits=total_cache_hits,
            kept_files=kept_list,
            pruned_files=pruned_list,
            loc_reduction_percentage=round(loc_reduction, 2),
            file_reduction_percentage=round(file_reduction, 2),
        )

        return current_state, result

    def _extract_removable_directories(self, state: CandidateState) -> List[str]:
        """
        Extracts unique directory prefixes from active files, sorted from deepest to shallowest,
        excluding directories that contain essential or protected files.
        """
        dir_set: Set[str] = set()
        for f in state.active_files:
            p = Path(f)
            # Add all parent directory prefixes
            for parent in p.parents:
                posix_parent = parent.as_posix()
                if posix_parent and posix_parent != ".":
                    dir_set.add(posix_parent)

        # Exclude directories containing protected or essential files
        forbidden_dirs: Set[str] = set()
        for protected in self.protected_files | state.essential_files:
            p = Path(protected)
            for parent in p.parents:
                posix_parent = parent.as_posix()
                if posix_parent and posix_parent != ".":
                    forbidden_dirs.add(posix_parent)

        removable_dirs = [d for d in dir_set if d not in forbidden_dirs]
        # Sort by depth descending (deepest first), then name
        removable_dirs.sort(key=lambda d: (-d.count("/"), -len(d), d))
        return removable_dirs
