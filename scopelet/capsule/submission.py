"""
Patch creation and submission engine for Scopelet reproduction capsules.
Verifies candidate fixes, validates file edit boundaries and generates solution.patch with solution.json.
"""

from __future__ import annotations

import datetime
import difflib
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import zipfile
from pydantic import BaseModel, Field

from .models import CapsuleManifest, SolutionMetadata, SolutionVerification
from .solver import CapsuleSolver, SolverStatus
from .runner import CapsuleRunner


class SubmissionError(Exception):
    """Base exception for solution submission errors."""
    pass


class UnauthorizedModificationError(SubmissionError):
    """Raised when edits touch files outside allowed_changes."""
    pass


class VerificationError(SubmissionError):
    """Raised when pre-submission test execution fails."""
    pass


class SubmissionResult(BaseModel):
    """
    Outcome of candidate solution patch creation and packaging.
    """
    workspace_dir: str = Field(..., description="Extracted capsule workspace")
    patch_file: str = Field(..., description="Absolute path to created solution.patch")
    metadata_file: str = Field(..., description="Absolute path to created solution.json")
    patch_hash: str = Field(..., description="SHA-256 hash of solution.patch")
    modified_files: List[str] = Field(default_factory=list, description="List of modified allowed files")
    is_compliant: bool = Field(..., description="Whether workspace strictly adheres to allowed_changes")
    verified: bool = Field(..., description="Whether verification tests passed before submission")
    metadata: SolutionMetadata = Field(..., description="Solution metadata specification")


class SubmissionEngine:
    """
    Manages the validation, verification and packaging of candidate bugfix patches.
    """

    def __init__(
        self,
        workspace_dir: Path,
        baseline_dir: Optional[Path] = None,
        capsule_archive: Optional[Path] = None,
        runner: Optional[CapsuleRunner] = None,
    ):
        self.workspace_dir = workspace_dir.resolve()
        self.baseline_dir = baseline_dir.resolve() if baseline_dir else None
        self.capsule_archive = capsule_archive.resolve() if capsule_archive else None
        self.runner = runner or CapsuleRunner()

    def _resolve_baseline_content(self, rel_path: str) -> str:
        """
        Locates the original content of a file from baseline storage or capsule archive.
        """
        # 1. Check explicit baseline directory
        if self.baseline_dir:
            candidate = self.baseline_dir / rel_path
            if candidate.exists():
                return candidate.read_text(encoding="utf-8", errors="replace")

        # 2. Check .scopelet/baseline inside workspace
        ws_baseline = self.workspace_dir / ".scopelet" / "baseline" / rel_path
        if ws_baseline.exists():
            return ws_baseline.read_text(encoding="utf-8", errors="replace")

        # 3. Check explicitly provided capsule archive
        if self.capsule_archive and self.capsule_archive.exists():
            with zipfile.ZipFile(self.capsule_archive, "r") as zf:
                try:
                    return zf.read(rel_path).decode("utf-8", errors="replace")
                except KeyError:
                    pass

        # 4. Search for archive in workspace or parent directory
        candidates = [
            self.workspace_dir / f"{self.workspace_dir.name}.scopelet",
            self.workspace_dir.parent / f"{self.workspace_dir.name}.scopelet",
        ]
        for archive_path in candidates:
            if archive_path.exists():
                try:
                    with zipfile.ZipFile(archive_path, "r") as zf:
                        return zf.read(rel_path).decode("utf-8", errors="replace")
                except Exception:
                    pass

        raise FileNotFoundError(
            f"Original baseline content for '{rel_path}' could not be located. "
            f"Ensure .scopelet/baseline exists or provide the original .scopelet archive."
        )

    def generate_patch(self, modified_files: List[str]) -> str:
        """
        Generates a standard unified diff across all modified allowed files.
        """
        diff_chunks: List[str] = []

        for rel_path in sorted(modified_files):
            current_file = self.workspace_dir / rel_path
            curr_text = current_file.read_text(encoding="utf-8", errors="replace") if current_file.exists() else ""
            orig_text = self._resolve_baseline_content(rel_path)

            orig_lines = orig_text.splitlines(keepends=True)
            curr_lines = curr_text.splitlines(keepends=True)

            diff_lines = list(
                difflib.unified_diff(
                    orig_lines,
                    curr_lines,
                    fromfile=f"a/{rel_path}",
                    tofile=f"b/{rel_path}",
                )
            )

            if diff_lines:
                diff_chunks.append("".join(diff_lines))

        patch_output = "".join(diff_chunks)
        if patch_output and not patch_output.endswith("\n"):
            patch_output += "\n"

        return patch_output

    def create_submission(
        self,
        author: Optional[str] = None,
        summary: Optional[str] = None,
        verify: bool = True,
        output_dir: Optional[Path] = None,
    ) -> SubmissionResult:
        """
        Validates compliance, executes pre-submission verification and writes solution files.
        """
        manifest_file = self.workspace_dir / "capsule.json"
        if not manifest_file.exists():
            raise FileNotFoundError(f"Missing capsule.json in workspace: {self.workspace_dir}")

        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        manifest = CapsuleManifest.model_validate(manifest_data)

        # 1. Enforce strict edit compliance
        status: SolverStatus = CapsuleSolver.get_status(self.workspace_dir)

        if status.modified_forbidden:
            forbidden_list = ", ".join(status.modified_forbidden)
            raise UnauthorizedModificationError(
                f"Unauthorized modifications detected in forbidden files: {forbidden_list}"
            )

        if status.added_files:
            added_list = ", ".join(status.added_files)
            raise UnauthorizedModificationError(
                f"Unauthorized new files detected in workspace: {added_list}"
            )

        if status.deleted_files:
            deleted_list = ", ".join(status.deleted_files)
            raise UnauthorizedModificationError(
                f"Files missing from capsule baseline: {deleted_list}"
            )

        if not status.modified_allowed:
            raise SubmissionError(
                "No modifications detected in allowed files. Implement a fix before submitting."
            )

        # 2. Pre-submission verification
        verification_info: Optional[SolutionVerification] = None
        if verify:
            manifest_run, result = self.runner.run(capsule_target=self.workspace_dir)
            if result.exit_code != 0:
                raise VerificationError(
                    f"Verification command '{manifest.command}' failed with exit code {result.exit_code}."
                )

            verification_info = SolutionVerification(
                command=manifest.command,
                exit_code=result.exit_code,
                success=True,
                duration_ms=result.duration_ms,
            )

        # 3. Generate unified diff solution.patch
        patch_text = self.generate_patch(status.modified_allowed)
        if not patch_text.strip():
            raise SubmissionError("Generated solution.patch is empty despite detected changes.")

        patch_hash = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()

        # 4. Write solution.patch and solution.json
        target_out = (output_dir or self.workspace_dir).resolve()
        target_out.mkdir(parents=True, exist_ok=True)

        patch_path = target_out / "solution.patch"
        patch_path.write_text(patch_text, encoding="utf-8")

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        author_id = author or "external_solver"

        metadata = SolutionMetadata(
            schema_version="1.0",
            capsule_hash=manifest.capsule_hash,
            patch_hash=patch_hash,
            modified_files=status.modified_allowed,
            created_at=now_utc,
            author=author_id,
            verification=verification_info,
            summary=summary,
        )

        metadata_path = target_out / "solution.json"
        metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

        return SubmissionResult(
            workspace_dir=str(self.workspace_dir),
            patch_file=str(patch_path),
            metadata_file=str(metadata_path),
            patch_hash=patch_hash,
            modified_files=status.modified_allowed,
            is_compliant=True,
            verified=verify,
            metadata=metadata,
        )
