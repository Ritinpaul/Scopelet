"""
Patch reintegration engine package.
Includes identifier reverse mapping, isolated worktree management,
V1 exact application and V2 semantic drift-tolerant patch application.
"""

from .applier import ReintegrationApplierV1, ReintegrationResult
from .mapper import ReverseIdentifierMapper
from .semantic_applier import (
    HunkMatch,
    SemanticPatchApplierV2,
    SemanticReintegrationResult,
)
from .worktree import IsolatedWorktree

__all__ = [
    "IsolatedWorktree",
    "ReverseIdentifierMapper",
    "ReintegrationApplierV1",
    "ReintegrationResult",
    "SemanticPatchApplierV2",
    "SemanticReintegrationResult",
    "HunkMatch",
]
