"""
Patch reintegration engine V1.
Reverses identifier sanitization and applies patches to clean repository worktrees.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from .mapper import ReverseIdentifierMapper
from .worktree import IsolatedWorktree
from ..verification.patcher import PatchApplier, PatchError


class ReintegrationResult(BaseModel):
    """
    Outcome of patch reintegration into private repository workspace.
    """
    success: bool = Field(..., description="Whether patch application succeeded cleanly")
    un_sanitized_patch: str = Field(..., description="Patch with original identifiers restored")
    modified_files: List[str] = Field(default_factory=list, description="Files modified by patch")
    error: Optional[str] = Field(default=None, description="Error message if application failed")


class ReintegrationApplierV1:
    """
    Reintegration engine applying candidate patches back to private codebases.
    """

    def __init__(
        self,
        repo_dir: Path,
        mapping: Optional[Dict[str, str]] = None,
        mapping_file: Optional[Path] = None,
    ):
        self.repo_dir = repo_dir.resolve()
        if mapping:
            self.mapper = ReverseIdentifierMapper(mapping)
        elif mapping_file and mapping_file.exists():
            self.mapper = ReverseIdentifierMapper.from_file(mapping_file)
        else:
            default_map = self.repo_dir / ".scopelet" / "private" / "mapping.json"
            if default_map.exists():
                self.mapper = ReverseIdentifierMapper.from_file(default_map)
            else:
                self.mapper = ReverseIdentifierMapper({})

    def apply(self, patch_content: str, target_dir: Optional[Path] = None) -> ReintegrationResult:
        """
        Un-sanitizes the patch and applies it to target_dir.
        """
        dest = (target_dir or self.repo_dir).resolve()
        un_sanitized = self.mapper.un_sanitize_patch(patch_content)

        try:
            modified = PatchApplier.apply_patch(un_sanitized, dest)
            return ReintegrationResult(
                success=True,
                un_sanitized_patch=un_sanitized,
                modified_files=modified,
                error=None,
            )
        except PatchError as pe:
            return ReintegrationResult(
                success=False,
                un_sanitized_patch=un_sanitized,
                modified_files=[],
                error=f"V1 patch application failed: {pe}. Use Semantic Reintegration V2 for context drift.",
            )
        except Exception as e:
            return ReintegrationResult(
                success=False,
                un_sanitized_patch=un_sanitized,
                modified_files=[],
                error=f"Unexpected error during patch application: {e}",
            )
