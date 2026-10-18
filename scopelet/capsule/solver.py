"""
External Solver Mode for reproduction capsules.
Handles capsule opening, verification status inspection and workspace change tracking.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from .models import CapsuleManifest
from .packager import CapsulePackager


class SolverStatus(BaseModel):
    """
    Status of solver modifications inside an extracted capsule workspace.
    """
    workspace_dir: str = Field(..., description="Path to capsule workspace")
    is_compliant: bool = Field(..., description="Whether all edits are strictly within allowed files")
    modified_allowed: List[str] = Field(default_factory=list, description="Permitted files that were modified")
    modified_forbidden: List[str] = Field(default_factory=list, description="Unauthorized files that were modified")
    added_files: List[str] = Field(default_factory=list, description="Unexpected new files added to the workspace")
    deleted_files: List[str] = Field(default_factory=list, description="Files in the manifest that were deleted")
    untouched_allowed: List[str] = Field(default_factory=list, description="Permitted files that remain unchanged")

    def format_text(self) -> str:
        """Formats a human-readable status summary."""
        lines = []
        if self.is_compliant:
            lines.append("Compliance: PASS (All changes strictly within permitted files)")
        else:
            lines.append("Compliance: FAIL (Unauthorized changes detected)")

        if self.modified_allowed:
            lines.append(f"Modified Allowed ({len(self.modified_allowed)}):")
            for f in self.modified_allowed:
                lines.append(f"  [+] {f}")

        if self.modified_forbidden:
            lines.append(f"Unauthorized Modifications ({len(self.modified_forbidden)}):")
            for f in self.modified_forbidden:
                lines.append(f"  [!] {f} (FORBIDDEN)")

        if self.added_files:
            lines.append(f"Unauthorized New Files ({len(self.added_files)}):")
            for f in self.added_files:
                lines.append(f"  [!] {f} (UNTRACKED)")

        if self.deleted_files:
            lines.append(f"Deleted Files ({len(self.deleted_files)}):")
            for f in self.deleted_files:
                lines.append(f"  [-] {f}")

        if self.untouched_allowed:
            lines.append(f"Untouched Allowed ({len(self.untouched_allowed)}):")
            for f in self.untouched_allowed:
                lines.append(f"  [.] {f}")

        return "\n".join(lines)


class CapsuleSolver:
    """
    Assists external agents and developers in opening capsules and checking fix compliance.
    """

    IGNORE_METADATA_FILES = {
        "capsule.json",
        "task.yaml",
        "README.md",
        "solution.patch",
        "solution.json",
    }

    @staticmethod
    def get_open_display(manifest: CapsuleManifest) -> str:
        """
        Formats the standardized 4-line solver display:
        Task:     <title>
        Run:      <command>
        Failure:  <failure_description or failure_fingerprint>
        Editable: <comma-separated allowed_changes>
        """
        failure_str = manifest.failure_description or manifest.failure_fingerprint or "Test failure"
        editable_str = ", ".join(manifest.allowed_changes) if manifest.allowed_changes else "(None)"

        return (
            f"{'Task:':<10}{manifest.title}\n"
            f"{'Run:':<10}{manifest.command}\n"
            f"{'Failure:':<10}{failure_str}\n"
            f"{'Editable:':<10}{editable_str}"
        )

    @classmethod
    def open_capsule(
        cls,
        capsule_path: Path,
        extract_to: Optional[Path] = None,
    ) -> tuple[CapsuleManifest, Path, str]:
        """
        Extracts a .scopelet archive to target directory and returns the manifest, extracted path and display text.
        """
        archive = capsule_path.resolve()
        if not archive.exists():
            raise FileNotFoundError(f"Capsule archive not found: {archive}")

        target_dir = (extract_to or (archive.parent / archive.stem)).resolve()
        CapsulePackager.unpack(archive, target_dir)

        manifest_file = target_dir / "capsule.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Capsule archive missing capsule.json in root: {target_dir}")

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = CapsuleManifest.model_validate(manifest_data)
        display_text = cls.get_open_display(manifest)

        # Snapshot pristine baseline files for patch generation
        cls.snapshot_baseline(target_dir)

        return manifest, target_dir, display_text

    @classmethod
    def snapshot_baseline(cls, workspace_dir: Path) -> Path:
        """
        Snapshots current workspace files as baseline in .scopelet/baseline.
        """
        ws = workspace_dir.resolve()
        manifest_file = ws / "capsule.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Missing capsule.json in workspace: {ws}")

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = CapsuleManifest.model_validate(manifest_data)
        baseline_dir = ws / ".scopelet" / "baseline"
        baseline_dir.mkdir(parents=True, exist_ok=True)
        for cf in manifest.files:
            src = ws / cf.path
            dst = baseline_dir / cf.path
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(src.read_bytes())
        return baseline_dir

    @classmethod
    def get_status(cls, workspace_dir: Path) -> SolverStatus:
        """
        Inspects an extracted capsule workspace, comparing file hashes against the baseline manifest.
        """
        ws = workspace_dir.resolve()
        manifest_file = ws / "capsule.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Missing capsule.json in workspace: {ws}")

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = CapsuleManifest.model_validate(manifest_data)

        baseline_files: Dict[str, str] = {
            f.path: f.hash for f in manifest.files
        }
        allowed_set = set(manifest.allowed_changes)

        # Scan active files in workspace
        current_files: Dict[str, str] = {}
        for p in ws.rglob("*"):
            if not p.is_file():
                continue
            rel_posix = p.relative_to(ws).as_posix()

            # Ignore capsule metadata files and runner caches / dependencies
            if (
                rel_posix in cls.IGNORE_METADATA_FILES
                or rel_posix.startswith("node_modules/")
                or rel_posix.startswith(".git/")
                or rel_posix.startswith(".scopelet/")
            ):
                continue

            current_files[rel_posix] = hashlib.sha256(p.read_bytes()).hexdigest()

        modified_allowed: List[str] = []
        modified_forbidden: List[str] = []
        deleted_files: List[str] = []
        untouched_allowed: List[str] = []
        added_files: List[str] = []

        # Check baseline files
        for rel_path, baseline_hash in baseline_files.items():
            if rel_path not in current_files:
                deleted_files.append(rel_path)
            else:
                curr_hash = current_files[rel_path]
                if curr_hash != baseline_hash:
                    if rel_path in allowed_set:
                        modified_allowed.append(rel_path)
                    else:
                        modified_forbidden.append(rel_path)
                else:
                    if rel_path in allowed_set:
                        untouched_allowed.append(rel_path)

        # Check files added on disk that were not in baseline
        for rel_path in current_files:
            if rel_path not in baseline_files:
                if rel_path in allowed_set:
                    modified_allowed.append(rel_path)
                else:
                    added_files.append(rel_path)

        modified_allowed.sort()
        modified_forbidden.sort()
        added_files.sort()
        deleted_files.sort()
        untouched_allowed.sort()

        is_compliant = (
            len(modified_forbidden) == 0
            and len(added_files) == 0
            and len(deleted_files) == 0
        )

        return SolverStatus(
            workspace_dir=str(ws),
            is_compliant=is_compliant,
            modified_allowed=modified_allowed,
            modified_forbidden=modified_forbidden,
            added_files=added_files,
            deleted_files=deleted_files,
            untouched_allowed=untouched_allowed,
        )
