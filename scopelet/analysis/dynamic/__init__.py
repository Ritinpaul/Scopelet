"""
Dynamic analysis engine for Scopelet.
Provides V8 runtime tracing, coverage parsing and candidate slice synthesis.
"""

from .trace_parser import (
    DynamicTraceResult,
    FileCoverage,
    FunctionCoverage,
    normalize_v8_url,
    parse_v8_coverage_dir,
)
from .tracer import DynamicTracer, TraceExecutionReport
from .merger import CandidateSlice, compute_candidate_slice

__all__ = [
    "DynamicTraceResult",
    "FileCoverage",
    "FunctionCoverage",
    "normalize_v8_url",
    "parse_v8_coverage_dir",
    "DynamicTracer",
    "TraceExecutionReport",
    "CandidateSlice",
    "compute_candidate_slice",
]
