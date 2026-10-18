"""
Candidate slice merger combining static reachability, dynamic execution traces and stack frame roots.
"""

from typing import Set, List, Optional, Union
from pydantic import BaseModel, Field

from ..static.graph import DependencyGraph
from .trace_parser import DynamicTraceResult


class CandidateSlice(BaseModel):
    static_reachable: List[str] = Field(default_factory=list)
    dynamic_executed: List[str] = Field(default_factory=list)
    stack_frames: List[str] = Field(default_factory=list)
    combined_slice: List[str] = Field(default_factory=list)
    pruned_files: List[str] = Field(default_factory=list)
    total_files_count: int = 0
    slice_count: int = 0
    reduction_percentage: float = 0.0


def compute_candidate_slice(
    static_graph: DependencyGraph,
    dynamic_trace: Union[Set[str], DynamicTraceResult],
    stack_frames: List[str],
    all_files: Optional[Set[str]] = None,
) -> CandidateSlice:
    """
    Combines static dependency reachability, dynamic execution traces and stack frame roots
    to construct a minimal defect-preserving candidate slice.
    """
    repo_files: Set[str] = all_files or set(static_graph.nodes.keys())

    # Extract dynamic executed set
    if isinstance(dynamic_trace, DynamicTraceResult):
        dynamic_set = set(dynamic_trace.executed_files)
    else:
        dynamic_set = set(dynamic_trace)

    # Restrict dynamic files to repository boundaries
    dynamic_repo_files = {f for f in dynamic_set if f in repo_files or not repo_files}

    # Normalize stack frame entries
    normalized_stack_frames = [f for f in stack_frames if f]

    # Compute static reachability from stack frames and dynamic entries
    entry_points = list(dict.fromkeys(normalized_stack_frames + list(dynamic_repo_files)))
    static_reachable_set = static_graph.reachable(entry_points) if entry_points else set(repo_files)

    # Candidate set construction:
    # 1. Stack frames (guaranteed must-keep roots)
    candidate_set: Set[str] = set(normalized_stack_frames)

    # 2. Real dynamic executed files within repository
    candidate_set.update(dynamic_repo_files)

    # 3. Direct dependencies of dynamically executed files
    # (Preserves type definitions, interfaces and constants required for compilation)
    for dyn_file in dynamic_repo_files:
        for dep in static_graph.get_dependencies(dyn_file):
            if not repo_files or dep in repo_files:
                candidate_set.add(dep)

    # Fallback: if dynamic trace captured nothing (e.g. failure at pre-exec stage),
    # fall back to static reachability
    if not candidate_set and static_reachable_set:
        candidate_set = set(static_reachable_set)

    # If repo_files is specified, restrict candidates to repo files
    if repo_files:
        candidate_set = candidate_set.intersection(repo_files)

    combined_list = sorted(candidate_set)
    pruned_set = (repo_files - candidate_set) if repo_files else set()
    pruned_list = sorted(pruned_set)

    total_count = len(repo_files) if repo_files else len(combined_list)
    slice_count = len(combined_list)
    reduction = ((total_count - slice_count) / total_count * 100.0) if total_count > 0 else 0.0

    return CandidateSlice(
        static_reachable=sorted(static_reachable_set),
        dynamic_executed=sorted(dynamic_repo_files),
        stack_frames=normalized_stack_frames,
        combined_slice=combined_list,
        pruned_files=pruned_list,
        total_files_count=total_count,
        slice_count=slice_count,
        reduction_percentage=round(reduction, 2),
    )
