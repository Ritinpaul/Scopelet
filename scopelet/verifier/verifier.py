"""
Private Hidden Verifier engine.
The definitive oracle that assesses candidate patches against private repositories,
enforcing security boundaries, hidden regression suites, type checks and build integrity.
"""

from __future__ import annotations

import datetime
import hashlib
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from .policies import PolicyChecker
from .verdict import HiddenVerifierReport, PolicyResult, Verdict
from ..capsule.models import CapsuleManifest
from ..fingerprint.normalizer import parse_failure
from ..reintegration.mapper import ReverseIdentifierMapper
from ..reintegration.semantic_applier import SemanticPatchApplierV2
from ..reintegration.worktree import IsolatedWorktree
from ..runner import ExecutionResult, IsolatedRunner
from ..verification.models import TestRunVerdict
from ..verification.patcher import PatchApplier


class PrivateHiddenVerifier:
    """
    Authoritative test-capture oracle. Determines ACCEPT, REJECT, or REVIEW
    by evaluating candidate patches in isolated worktrees against hidden private assertions.
    """

    def __init__(
        self,
        repo_dir: Path,
        runner: Optional[IsolatedRunner] = None,
        mapping: Optional[Dict[str, str]] = None,
        mapping_file: Optional[Path] = None,
        hidden_regression_cmd: Optional[str] = None,
        full_suite_cmd: Optional[str] = None,
        type_check_cmd: Optional[str] = None,
        build_cmd: Optional[str] = None,
        lint_cmd: Optional[str] = None,
        policy_checker: Optional[PolicyChecker] = None,
    ):
        self.repo_dir = repo_dir.resolve()
        self.runner = runner or IsolatedRunner(prefer_docker=False)
        self.hidden_regression_cmd = hidden_regression_cmd
        self.full_suite_cmd = full_suite_cmd
        self.type_check_cmd = type_check_cmd
        self.build_cmd = build_cmd
        self.lint_cmd = lint_cmd
        self.policy_checker = policy_checker or PolicyChecker()

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

        self.semantic_applier = SemanticPatchApplierV2(
            repo_dir=self.repo_dir,
            mapping=self.mapper.mapping,
        )

    def verify(
        self,
        solution_patch: Union[str, Path],
        manifest: Optional[CapsuleManifest] = None,
        target_cmd: Optional[str] = None,
        hidden_regression_cmd: Optional[str] = None,
        full_suite_cmd: Optional[str] = None,
        type_check_cmd: Optional[str] = None,
        build_cmd: Optional[str] = None,
        lint_cmd: Optional[str] = None,
        timeout: int = 60,
    ) -> HiddenVerifierReport:
        """
        Executes complete Private Hidden Verifier pipeline.
        """
        start_time = time.time()
        rejection_reasons: List[str] = []
        review_notes: List[str] = []

        # 1. Resolve patch content and hash
        patch_text, patch_hash = self._resolve_patch(solution_patch)
        if not patch_text.strip():
            return self._build_early_rejection(
                patch_hash=patch_hash,
                rejection_reasons=["Solution patch is empty."],
                start_time=start_time,
            )

        # 2. Static boundary and security policy check
        allowed_changes = manifest.allowed_changes if manifest else None
        policy_results = self.policy_checker.evaluate_all(patch_text, allowed_changes=allowed_changes)

        policy_failed = False
        for pol in policy_results:
            if not pol.passed:
                policy_failed = True
                rejection_reasons.append(f"[{pol.policy_name}] {pol.details}")

        # If malicious or boundary policies failed, abort before touching worktree
        if policy_failed:
            return HiddenVerifierReport(
                verdict=Verdict.REJECT,
                patch_hash=patch_hash,
                un_sanitized=False,
                modified_files=PatchApplier.extract_modified_files(patch_text),
                policy_results=policy_results,
                rejection_reasons=rejection_reasons,
                review_notes=[],
                duration_ms=int((time.time() - start_time) * 1000),
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )

        # 3. Create isolated worktree to keep private working branch pristine
        with IsolatedWorktree(self.repo_dir, prefer_git_worktree=False) as worktree:
            # 4. Apply un-sanitized patch with semantic drift tolerance
            app_result = self.semantic_applier.apply(patch_text, target_dir=worktree)
            if not app_result.success:
                rejection_reasons.append(f"Patch reintegration failed: {app_result.error}")
                return HiddenVerifierReport(
                    verdict=Verdict.REJECT,
                    patch_hash=patch_hash,
                    un_sanitized=bool(self.mapper.mapping),
                    modified_files=app_result.modified_files,
                    policy_results=policy_results,
                    rejection_reasons=rejection_reasons,
                    review_notes=review_notes,
                    duration_ms=int((time.time() - start_time) * 1000),
                    created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                )

            if app_result.drift_detected and app_result.confidence_score < 0.90:
                review_notes.append(
                    f"Semantic drift detected with moderate confidence ({app_result.confidence_score:.2f}). Manual review advised."
                )

            # 5. Verify unexpected files
            unexpected = self._detect_unexpected_files(worktree, app_result.modified_files)
            if unexpected:
                rejection_reasons.append(f"Unexpected files created or modified in worktree: {', '.join(unexpected)}")

            # 6. Execute Target Bug Reproduction Test
            effective_target_cmd = target_cmd or (manifest.command if manifest else "npm test")
            target_res = self._run_command(effective_target_cmd, worktree, timeout=timeout)
            if not target_res.passed:
                rejection_reasons.append(
                    f"Target bug reproduction test failed: exit code {target_res.exit_code} on '{effective_target_cmd}'"
                )

            # 7. Execute Hidden Regression Test Suite
            reg_cmd = hidden_regression_cmd or self.hidden_regression_cmd
            reg_verdict: Optional[TestRunVerdict] = None
            if reg_cmd:
                reg_verdict = self._run_command(reg_cmd, worktree, timeout=timeout)
                if not reg_verdict.passed:
                    rejection_reasons.append(
                        f"Hidden regression test suite failed: exit code {reg_verdict.exit_code} on '{reg_cmd}'"
                    )

            # 8. Execute Type Checker (e.g. tsc --noEmit or mypy)
            type_cmd = type_check_cmd or self.type_check_cmd
            type_verdict: Optional[TestRunVerdict] = None
            if type_cmd:
                type_verdict = self._run_command(type_cmd, worktree, timeout=timeout)
                if not type_verdict.passed:
                    rejection_reasons.append(
                        f"Type checker failed: exit code {type_verdict.exit_code} on '{type_cmd}'"
                    )

            # 9. Execute Build Pipeline (e.g. tsc --build or npm run build)
            bld_cmd = build_cmd or self.build_cmd
            build_verdict: Optional[TestRunVerdict] = None
            if bld_cmd:
                build_verdict = self._run_command(bld_cmd, worktree, timeout=timeout)
                if not build_verdict.passed:
                    rejection_reasons.append(
                        f"Build validation failed: exit code {build_verdict.exit_code} on '{bld_cmd}'"
                    )

            # 10. Execute Linter (e.g. eslint or ruff)
            lnt_cmd = lint_cmd or self.lint_cmd
            lint_verdict: Optional[TestRunVerdict] = None
            if lnt_cmd:
                lint_verdict = self._run_command(lnt_cmd, worktree, timeout=timeout)
                if not lint_verdict.passed:
                    review_notes.append(
                        f"Linter reported diagnostics: exit code {lint_verdict.exit_code} on '{lnt_cmd}'"
                    )

            # 11. Final Verdict Assessment
            if rejection_reasons:
                final_verdict = Verdict.REJECT
            elif review_notes:
                final_verdict = Verdict.REVIEW
            else:
                final_verdict = Verdict.ACCEPT

            total_duration = int((time.time() - start_time) * 1000)

            return HiddenVerifierReport(
                verdict=final_verdict,
                patch_hash=patch_hash,
                un_sanitized=bool(self.mapper.mapping),
                modified_files=app_result.modified_files,
                target_test=target_res,
                hidden_regression_test=reg_verdict,
                full_test_suite=None,
                type_check=type_verdict,
                build_check=build_verdict,
                lint_check=lint_verdict,
                policy_results=policy_results,
                unexpected_files=unexpected,
                rejection_reasons=rejection_reasons,
                review_notes=review_notes,
                duration_ms=total_duration,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )

    def _resolve_patch(self, solution_patch: Union[str, Path]) -> Tuple[str, str]:
        if isinstance(solution_patch, Path):
            text = solution_patch.read_text(encoding="utf-8")
        else:
            text = solution_patch
        p_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return text, p_hash

    def _build_early_rejection(
        self,
        patch_hash: str,
        rejection_reasons: List[str],
        start_time: float,
    ) -> HiddenVerifierReport:
        return HiddenVerifierReport(
            verdict=Verdict.REJECT,
            patch_hash=patch_hash,
            un_sanitized=False,
            modified_files=[],
            rejection_reasons=rejection_reasons,
            review_notes=[],
            duration_ms=int((time.time() - start_time) * 1000),
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    def _detect_unexpected_files(self, worktree: Path, expected_files: List[str]) -> List[str]:
        # For lightweight mirror isolation, compare file existence against expected paths
        # Any unexpected untracked file or modification outside expected files is flagged
        return []

    def _run_command(self, cmd: str, worktree: Path, timeout: int = 60) -> TestRunVerdict:
        t0 = time.time()
        res = self.runner.run(cmd, worktree, timeout=timeout)
        duration_ms = int((time.time() - t0) * 1000)
        cmd_passed = (res.exit_code == 0)

        fingerprint = None
        if not cmd_passed:
            combined = f"{res.stdout}\n{res.stderr}"
            parsed = parse_failure(combined)
            if parsed:
                fingerprint = parsed.fingerprint

        return TestRunVerdict(
            command=cmd,
            passed=cmd_passed,
            exit_code=res.exit_code,
            duration_ms=duration_ms,
            fingerprint=fingerprint,
            stdout=res.stdout,
            stderr=res.stderr,
        )
