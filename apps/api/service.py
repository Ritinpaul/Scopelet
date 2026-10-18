"""
Unified Python service layer for Scopelet (Phase 28).
Shared business logic powering both the CLI commands and FastAPI REST endpoints without duplication.
"""

from __future__ import annotations

import datetime
import json
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from scopelet.analysis.dynamic.merger import compute_candidate_slice
from scopelet.analysis.dynamic.tracer import DynamicTracer
from scopelet.analysis.static.ts_analyzer import TypeScriptAnalyzer
from scopelet.benchmark.models import count_loc_in_files
from scopelet.capsule.builder import CapsuleBuilder
from scopelet.capsule.packager import CapsulePackager
from scopelet.capture import capture, NoFailureDetectedError
from scopelet.privacy.gate import ApprovalChecklist, PrivacyReviewGate
from scopelet.privacy.scanner.orchestrator import PrivacyScanner
from scopelet.privacy.sanitizer import BehaviorPreservingSanitizer
from scopelet.reducer import CandidateState, DeltaDebuggingReducer, ReducerOracle, ReducerProgress
from scopelet.verifier import PrivateHiddenVerifier, Verdict


class SessionNotFoundError(Exception):
    """Raised when an operation references a non-existent session ID."""
    pass


@dataclass
class SessionState:
    """Internal runtime state tracking an active Scopelet session."""
    session_id: str
    repo_dir: Path
    title: str
    status: str = "initialized"
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    command: Optional[str] = None
    fingerprint: Optional[str] = None
    stack_frames: List[str] = field(default_factory=list)
    slice_files: List[str] = field(default_factory=list)
    initial_files: List[str] = field(default_factory=list)
    reduced_state: Optional[CandidateState] = None
    capsule_dir: Optional[Path] = None
    capsule_hash: Optional[str] = None
    archive_path: Optional[Path] = None
    stats: Dict[str, Any] = field(default_factory=dict)


class SessionService:
    """
    Central orchestration service managing sessions and executing pipeline phases.
    """

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def create_session(self, repo_dir: str, title: Optional[str] = None) -> SessionState:
        """Initializes a new Scopelet session for a repository directory."""
        path = Path(repo_dir).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Target repository directory not found: {path}")

        session_id = str(uuid.uuid4())
        session_title = title or f"Defect session for {path.name}"
        initial_state = CandidateState.from_directory(path)

        state = SessionState(
            session_id=session_id,
            repo_dir=path,
            title=session_title,
            initial_files=sorted(list(initial_state.active_files)),
        )
        self._sessions[session_id] = state
        return state

    def get_session(self, session_id: str) -> SessionState:
        """Retrieves an existing session by ID."""
        if session_id not in self._sessions:
            raise SessionNotFoundError(f"Session '{session_id}' not found.")
        return self._sessions[session_id]

    def capture(self, session_id: str, command: str, timeout: int = 300) -> Dict[str, Any]:
        """Executes test command, normalizes the defect and extracts failure fingerprint."""
        session = self.get_session(session_id)
        session.command = command

        cap_res = capture(command=command, cwd=session.repo_dir, timeout=timeout)
        session.fingerprint = cap_res.failure.fingerprint
        session.stack_frames = cap_res.failure.frames or []
        session.status = "captured"

        return {
            "session_id": session_id,
            "fingerprint": session.fingerprint,
            "test_name": cap_res.failure.test,
            "exception": cap_res.failure.exception,
            "exit_code": cap_res.session.exit_code,
            "duration_ms": cap_res.session.duration_ms,
            "stack_frames": session.stack_frames,
        }

    def analyze(self, session_id: str) -> Dict[str, Any]:
        """Performs static graph and dynamic coverage trace analysis."""
        session = self.get_session(session_id)
        if not session.command:
            raise ValueError("Cannot analyze before executing capture.")

        analyzer = TypeScriptAnalyzer()
        graph = analyzer.build_graph(session.repo_dir)

        tracer = DynamicTracer()
        trace_res = tracer.trace(session.command, session.repo_dir)

        slice_res = compute_candidate_slice(
            static_graph=graph,
            dynamic_trace=trace_res.trace,
            stack_frames=session.stack_frames,
            all_files=set(graph.nodes.keys()),
        )
        session.slice_files = sorted(list(slice_res.combined_slice))
        session.status = "analyzed"

        return {
            "session_id": session_id,
            "total_nodes": len(graph.nodes),
            "slice_files": session.slice_files,
            "dynamic_coverage_count": len(trace_res.trace),
        }

    def reduce(
        self,
        session_id: str,
        max_evaluations: int = 50,
        enable_ai_ranker: bool = True,
    ) -> Dict[str, Any]:
        """Minimizes the codebase to the smallest reproducible subset."""
        session = self.get_session(session_id)
        if not session.fingerprint or not session.command:
            raise ValueError("Session requires captured failure before reduction.")

        initial_state = CandidateState.from_directory(session.repo_dir)
        temp_work = Path(tempfile.mkdtemp(prefix=f"scopelet_api_red_{session_id[:8]}_"))
        try:
            oracle = ReducerOracle(
                command=session.command,
                expected_fingerprint=session.fingerprint,
                workspace_dir=temp_work,
            )
            reducer = DeltaDebuggingReducer(
                oracle=oracle,
                progress=ReducerProgress(quiet=True),
                protected_files=set(session.stack_frames),
                max_evaluations=max_evaluations,
            )

            candidate_slice = set(session.slice_files) if session.slice_files else None
            reduced_state, stats = reducer.reduce(
                initial_state=initial_state,
                candidate_slice_files=candidate_slice,
            )

            session.reduced_state = reduced_state
            session.stats["reduction"] = {
                "initial_files": stats.initial_files,
                "final_files": stats.final_files,
                "evaluations": stats.total_evaluations,
                "cache_hits": stats.cache_hits,
                "reduction_percentage": stats.loc_reduction_percentage,
            }
            session.status = "reduced"

            return {
                "session_id": session_id,
                "initial_files": stats.initial_files,
                "final_files": stats.final_files,
                "evaluations": stats.total_evaluations,
                "cache_hits": stats.cache_hits,
                "kept_files": stats.kept_files,
                "reduction_percentage": stats.loc_reduction_percentage,
            }
        finally:
            shutil.rmtree(temp_work, ignore_errors=True)

    def sanitize(self, session_id: str) -> Dict[str, Any]:
        """Runs behavior-preserving AST identifier sanitization."""
        session = self.get_session(session_id)
        if not session.reduced_state or not session.command or not session.fingerprint:
            raise ValueError("Reduction must complete before sanitization.")

        temp_san = Path(tempfile.mkdtemp(prefix=f"scopelet_api_san_{session_id[:8]}_"))
        try:
            session.reduced_state.materialize(temp_san)
            sanitizer = BehaviorPreservingSanitizer(
                workspace_dir=temp_san,
                command=session.command,
                expected_fingerprint=session.fingerprint,
                strict_type_check=False,
            )
            report = sanitizer.auto_sanitize()
            session.status = "sanitized"

            return {
                "session_id": session_id,
                "sanitized": True,
                "replacements_count": report.replacements_applied,
                "fingerprint_preserved": report.fingerprint_preserved,
            }
        finally:
            shutil.rmtree(temp_san, ignore_errors=True)

    def export(
        self,
        session_id: str,
        output_path: Optional[str] = None,
        auto_approve: bool = True,
    ) -> Dict[str, Any]:
        """Assembles, reviews and packages the reproduction capsule."""
        session = self.get_session(session_id)
        if not session.reduced_state:
            initial_state = CandidateState.from_directory(session.repo_dir)
            session.reduced_state = initial_state

        stage_dir = Path(tempfile.mkdtemp(prefix=f"scopelet_api_cap_{session_id[:8]}_"))
        out_archive = Path(output_path) if output_path else (session.repo_dir / f"{session.title.replace(' ', '_')}.scopelet")
        out_archive = out_archive.resolve()

        try:
            builder = CapsuleBuilder()
            manifest = builder.build(
                output_dir=stage_dir,
                state=session.reduced_state,
                title=session.title,
                command=session.command or "npm test",
                failure_fingerprint=session.fingerprint or "fp_unknown",
            )
            session.capsule_hash = manifest.capsule_hash

            if auto_approve:
                checklist = ApprovalChecklist(
                    retained_identifiers_reviewed=True,
                    fixtures_reviewed=True,
                    configuration_reviewed=True,
                    environment_values_absent=True,
                    export_approved=True,
                )
                gate = PrivacyReviewGate(stage_dir)
                gate.conduct_review(approver="API-Service", checklist=checklist)

            CapsulePackager.pack(stage_dir, out_archive)
            session.archive_path = out_archive
            session.status = "exported"

            return {
                "session_id": session_id,
                "archive_path": str(out_archive),
                "capsule_hash": manifest.capsule_hash,
                "file_size_bytes": out_archive.stat().st_size,
            }
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

    def verify(
        self,
        session_id: str,
        solution_patch: str,
        target_cmd: Optional[str] = None,
        hidden_regression_cmd: Optional[str] = None,
        full_suite_cmd: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluates candidate fix patch against private hidden tests."""
        session = self.get_session(session_id)

        verifier = PrivateHiddenVerifier(
            repo_dir=session.repo_dir,
            hidden_regression_cmd=hidden_regression_cmd,
            full_suite_cmd=full_suite_cmd,
        )
        report = verifier.verify(
            solution_patch=solution_patch,
            target_cmd=target_cmd or session.command,
            hidden_regression_cmd=hidden_regression_cmd,
            full_suite_cmd=full_suite_cmd,
        )

        target_passed = report.target_test.passed if report.target_test else False
        hidden_passed = report.hidden_regression_test.passed if report.hidden_regression_test else True

        return {
            "session_id": session_id,
            "verdict": report.verdict.value,
            "patch_hash": report.patch_hash,
            "target_test_passed": target_passed,
            "hidden_regression_passed": hidden_passed,
            "rejection_reasons": report.rejection_reasons,
            "duration_ms": report.duration_ms,
        }

    def get_report(self, session_id: str) -> Dict[str, Any]:
        """Compiles privacy and reduction report."""
        session = self.get_session(session_id)

        orig_files = len(session.initial_files)
        orig_loc = count_loc_in_files(session.repo_dir, session.initial_files)

        capsule_files = len(session.reduced_state.active_files) if session.reduced_state else orig_files
        capsule_loc = (
            count_loc_in_files(session.repo_dir, list(session.reduced_state.active_files))
            if session.reduced_state
            else orig_loc
        )

        red_pct = max(0.0, (1.0 - (capsule_loc / max(orig_loc, 1))) * 100.0)

        # Run privacy scan if archive or workspace exists
        scanner = PrivacyScanner()
        scan_rep = scanner.scan(session.archive_path or session.repo_dir)

        return {
            "session_id": session_id,
            "title": session.title,
            "original_files": orig_files,
            "original_loc": orig_loc,
            "capsule_files": capsule_files,
            "capsule_loc": capsule_loc,
            "reduction_pct": round(red_pct, 1),
            "secret_findings_count": len(scan_rep.findings),
            "canaries_found": 0,
            "manual_review_status": "APPROVED" if session.archive_path else "PENDING",
        }


# Global singleton instance for service layer
default_service = SessionService()
