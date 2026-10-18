"""
Private repository ingestion and verification engine.
Validates patch integrity, checks boundary compliance and executes isolated test verdicts.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import zipfile

from ..capsule.models import CapsuleManifest, SolutionMetadata
from ..capsule.packager import CapsulePackager
from ..reducer.candidate import link_directory
from ..runner import IsolatedRunner, ExecutionResult
from .models import TestRunVerdict, VerificationReport
from .patcher import PatchApplier, PatchError


class VerificationEngine:
    """
    Ingests candidate bugfix patches, enforces task constraints and runs isolated tests.
    """

    def __init__(
        self,
        repo_dir: Optional[Path] = None,
        runner: Optional[IsolatedRunner] = None,
    ):
        self.repo_dir = (repo_dir or Path.cwd()).resolve()
        self.runner = runner or IsolatedRunner(prefer_docker=False)

    def verify_solution(
        self,
        solution_target: Path,
        manifest_target: Optional[Path] = None,
        command: Optional[str] = None,
        regression_cmd: Optional[str] = None,
        timeout: int = 60,
        output_dir: Optional[Path] = None,
    ) -> VerificationReport:
        """
        Executes complete verification flow for a solution patch against the private repository.
        """
        target = solution_target.resolve()
        rejection_reasons: List[str] = []

        # 1. Resolve patch file and metadata
        patch_file, solution_metadata = self._resolve_solution_artifacts(target)
        if not patch_file.exists():
            raise FileNotFoundError(f"Solution patch not found: {patch_file}")

        patch_content = patch_file.read_text(encoding="utf-8")
        if not patch_content.strip():
            rejection_reasons.append("Solution patch is empty.")

        patch_hash = hashlib.sha256(patch_content.encode("utf-8")).hexdigest()

        # 2. Validate metadata integrity if solution.json exists
        if solution_metadata:
            if solution_metadata.patch_hash != patch_hash:
                rejection_reasons.append(
                    f"Patch hash mismatch: solution.json specifies {solution_metadata.patch_hash} "
                    f"but actual patch hash is {patch_hash}."
                )

        # 3. Resolve manifest if provided
        manifest = self._resolve_manifest(manifest_target)
        if manifest and solution_metadata:
            if solution_metadata.capsule_hash and solution_metadata.capsule_hash != manifest.capsule_hash:
                rejection_reasons.append(
                    f"Capsule hash mismatch: solution.json references {solution_metadata.capsule_hash} "
                    f"while target manifest is {manifest.capsule_hash}."
                )

        # 4. Enforce file boundary compliance
        modified_files = PatchApplier.extract_modified_files(patch_content)
        compliance_passed = True

        if manifest and manifest.allowed_changes:
            allowed_set = set(manifest.allowed_changes)
            unauthorized = [f for f in modified_files if f not in allowed_set]
            if unauthorized:
                compliance_passed = False
                unauthorized_str = ", ".join(unauthorized)
                rejection_reasons.append(
                    f"Unauthorized file modifications detected outside allowed_changes: {unauthorized_str}"
                )

        # Determine target verification command
        effective_cmd = command
        if not effective_cmd and manifest:
            effective_cmd = manifest.command
        if not effective_cmd:
            effective_cmd = "npm test"

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # If already rejected on static/boundary checks, return early verdict
        if rejection_reasons:
            dummy_verdict = TestRunVerdict(
                command=effective_cmd,
                passed=False,
                exit_code=1,
                duration_ms=0,
                stdout="",
                stderr="Execution aborted due to pre-flight integrity/boundary violations.",
            )
            return self._build_and_save_report(
                verdict="REJECTED",
                patch_hash=patch_hash,
                modified_files=modified_files,
                target_test=dummy_verdict,
                regression_test=None,
                compliance_passed=compliance_passed,
                rejection_reasons=rejection_reasons,
                created_at=now_utc,
                output_dir=output_dir,
            )

        # 5. Materialize clean sandbox of private repository
        staging_dir = Path(tempfile.mkdtemp(prefix="scopelet_verify_"))
        try:
            self._materialize_sandbox(self.repo_dir, staging_dir)

            # Apply patch to sandbox
            try:
                PatchApplier.apply_patch(patch_content, staging_dir)
            except PatchError as pe:
                rejection_reasons.append(f"Failed to apply patch: {pe}")
                dummy_verdict = TestRunVerdict(
                    command=effective_cmd,
                    passed=False,
                    exit_code=1,
                    duration_ms=0,
                    stdout="",
                    stderr=str(pe),
                )
                return self._build_and_save_report(
                    verdict="REJECTED",
                    patch_hash=patch_hash,
                    modified_files=modified_files,
                    target_test=dummy_verdict,
                    regression_test=None,
                    compliance_passed=compliance_passed,
                    rejection_reasons=rejection_reasons,
                    created_at=now_utc,
                    output_dir=output_dir,
                )

            # 6. Run target oracle verification test
            target_result: ExecutionResult = self.runner.run(
                command=effective_cmd,
                cwd=staging_dir,
                timeout=timeout,
                use_cache=False,
            )

            target_passed = (target_result.exit_code == 0)
            target_verdict = TestRunVerdict(
                command=effective_cmd,
                passed=target_passed,
                exit_code=target_result.exit_code,
                duration_ms=target_result.duration_ms,
                fingerprint=target_result.fingerprint,
                stdout=target_result.stdout,
                stderr=target_result.stderr,
            )

            if not target_passed:
                rejection_reasons.append(
                    f"Target test failed with exit code {target_result.exit_code}."
                )

            # 7. Optional regression suite verification
            regression_verdict: Optional[TestRunVerdict] = None
            if regression_cmd:
                reg_result: ExecutionResult = self.runner.run(
                    command=regression_cmd,
                    cwd=staging_dir,
                    timeout=timeout,
                    use_cache=False,
                )
                reg_passed = (reg_result.exit_code == 0)
                regression_verdict = TestRunVerdict(
                    command=regression_cmd,
                    passed=reg_passed,
                    exit_code=reg_result.exit_code,
                    duration_ms=reg_result.duration_ms,
                    fingerprint=reg_result.fingerprint,
                    stdout=reg_result.stdout,
                    stderr=reg_result.stderr,
                )

                if not reg_passed:
                    rejection_reasons.append(
                        f"Regression test suite failed with exit code {reg_result.exit_code}."
                    )

            overall_verdict = "ACCEPTED" if not rejection_reasons else "REJECTED"

            return self._build_and_save_report(
                verdict=overall_verdict,
                patch_hash=patch_hash,
                modified_files=modified_files,
                target_test=target_verdict,
                regression_test=regression_verdict,
                compliance_passed=compliance_passed,
                rejection_reasons=rejection_reasons,
                created_at=now_utc,
                output_dir=output_dir,
            )

        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    def _resolve_solution_artifacts(self, target: Path) -> tuple[Path, Optional[SolutionMetadata]]:
        """
        Locates the patch file and optional solution.json metadata from target path.
        """
        if target.is_file():
            if target.name.endswith(".patch"):
                meta_cand = target.parent / "solution.json"
                meta = self._load_solution_metadata(meta_cand) if meta_cand.exists() else None
                return target, meta
            elif target.name.endswith(".json"):
                meta = self._load_solution_metadata(target)
                patch_cand = target.parent / "solution.patch"
                return patch_cand, meta
            elif target.name.endswith(".zip"):
                # Extract archive into a temporary folder
                temp_extract = Path(tempfile.mkdtemp(prefix="scopelet_sol_zip_"))
                with zipfile.ZipFile(target, "r") as zf:
                    zf.extractall(temp_extract)
                patch_cand = temp_extract / "solution.patch"
                meta_cand = temp_extract / "solution.json"
                meta = self._load_solution_metadata(meta_cand) if meta_cand.exists() else None
                return patch_cand, meta

        if target.is_dir():
            patch_cand = target / "solution.patch"
            meta_cand = target / "solution.json"
            meta = self._load_solution_metadata(meta_cand) if meta_cand.exists() else None
            return patch_cand, meta

        raise FileNotFoundError(f"Invalid solution target: {target}")

    def _load_solution_metadata(self, path: Path) -> Optional[SolutionMetadata]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SolutionMetadata.model_validate(data)
        except Exception:
            return None

    def _resolve_manifest(self, manifest_target: Optional[Path]) -> Optional[CapsuleManifest]:
        """
        Loads CapsuleManifest from capsule.json or .scopelet archive if available.
        """
        if not manifest_target:
            local_capsule = self.repo_dir / ".scopelet" / "capsule.json"
            if local_capsule.exists():
                manifest_target = local_capsule
            else:
                return None

        path = manifest_target.resolve()
        if path.is_file():
            if path.name.endswith(".json"):
                data = json.loads(path.read_text(encoding="utf-8"))
                return CapsuleManifest.model_validate(data)
            elif path.name.endswith(".scopelet"):
                with zipfile.ZipFile(path, "r") as zf:
                    data = json.loads(zf.read("capsule.json").decode("utf-8"))
                    return CapsuleManifest.model_validate(data)
        elif path.is_dir():
            cand = path / "capsule.json"
            if cand.exists():
                data = json.loads(cand.read_text(encoding="utf-8"))
                return CapsuleManifest.model_validate(data)

        return None

    def _materialize_sandbox(self, src_repo: Path, dst_dir: Path) -> None:
        """
        Copies source files to sandbox and links node_modules for high execution speed.
        """
        dst_dir.mkdir(parents=True, exist_ok=True)
        for item in src_repo.iterdir():
            name = item.name
            if name in (".git", ".scopelet", ".pytest_cache", "__pycache__", "node_modules"):
                continue

            dest = dst_dir / name
            if item.is_dir():
                shutil.copytree(item, dest, ignore=shutil.ignore_patterns(".git", "__pycache__"))
            else:
                shutil.copy2(item, dest)

        # Link node_modules if present
        src_nm = src_repo / "node_modules"
        if src_nm.exists() and src_nm.is_dir():
            link_directory(src_nm, dst_dir / "node_modules")

    def _build_and_save_report(
        self,
        verdict: str,
        patch_hash: str,
        modified_files: List[str],
        target_test: TestRunVerdict,
        regression_test: Optional[TestRunVerdict],
        compliance_passed: bool,
        rejection_reasons: List[str],
        created_at: str,
        output_dir: Optional[Path],
    ) -> VerificationReport:
        report = VerificationReport(
            schema_version="1.0",
            verdict=verdict,  # type: ignore[arg-type]
            patch_hash=patch_hash,
            modified_files=modified_files,
            target_test=target_test,
            regression_test=regression_test,
            compliance_passed=compliance_passed,
            rejection_reasons=rejection_reasons,
            created_at=created_at,
        )

        out_target = (output_dir or (self.repo_dir / ".scopelet")).resolve()
        out_target.mkdir(parents=True, exist_ok=True)
        out_file = out_target / "verification.json"
        out_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        return report
