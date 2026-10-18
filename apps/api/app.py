"""
FastAPI application for Scopelet (Phase 28).
Exposes REST endpoints delegating to the unified SessionService layer.
"""

from __future__ import annotations

from typing import Any, Dict
from fastapi import FastAPI, HTTPException, status

from .schemas import (
    AnalyzeResponse,
    CaptureRequest,
    CaptureResponse,
    CreateSessionRequest,
    ExportRequest,
    ExportResponse,
    ReduceRequest,
    ReduceResponse,
    ReportResponse,
    SanitizeResponse,
    SessionResponse,
    VerifyRequest,
    VerifyResponse,
)
from .service import SessionNotFoundError, default_service

app = FastAPI(
    title="Scopelet API",
    description="REST API for behavior-preserving defect minimization and private hidden verification",
    version="1.0.0",
)


@app.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(req: CreateSessionRequest) -> SessionResponse:
    """Creates a new defect minimization session."""
    try:
        session = default_service.create_session(repo_dir=req.repo_dir, title=req.title)
        return SessionResponse(
            session_id=session.session_id,
            repo_dir=str(session.repo_dir),
            title=session.title,
            status=session.status,
            created_at=session.created_at,
            files_count=len(session.initial_files),
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    """Retrieves session metadata by ID."""
    try:
        s = default_service.get_session(session_id)
        red_count = len(s.reduced_state.active_files) if s.reduced_state else None
        return SessionResponse(
            session_id=s.session_id,
            repo_dir=str(s.repo_dir),
            title=s.title,
            status=s.status,
            created_at=s.created_at,
            fingerprint=s.fingerprint,
            files_count=len(s.initial_files),
            reduced_files_count=red_count,
            capsule_hash=s.capsule_hash,
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@app.post("/sessions/{session_id}/capture", response_model=CaptureResponse)
def capture_session(session_id: str, req: CaptureRequest) -> CaptureResponse:
    """Executes a test command and extracts the failure fingerprint."""
    try:
        res = default_service.capture(
            session_id=session_id,
            command=req.command,
            timeout=req.timeout,
        )
        return CaptureResponse(**res)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/sessions/{session_id}/analyze", response_model=AnalyzeResponse)
def analyze_session(session_id: str) -> AnalyzeResponse:
    """Runs static and dynamic reachability analysis."""
    try:
        res = default_service.analyze(session_id=session_id)
        return AnalyzeResponse(**res)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/sessions/{session_id}/reduce", response_model=ReduceResponse)
def reduce_session(session_id: str, req: ReduceRequest) -> ReduceResponse:
    """Executes delta-debugging minimization to isolate the defect subset."""
    try:
        res = default_service.reduce(
            session_id=session_id,
            max_evaluations=req.max_evaluations,
            enable_ai_ranker=req.enable_ai_ranker,
        )
        return ReduceResponse(**res)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/sessions/{session_id}/sanitize", response_model=SanitizeResponse)
def sanitize_session(session_id: str) -> SanitizeResponse:
    """Performs behavior-preserving AST renaming on the reduced candidate."""
    try:
        res = default_service.sanitize(session_id=session_id)
        return SanitizeResponse(**res)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/sessions/{session_id}/export", response_model=ExportResponse)
def export_session(session_id: str, req: ExportRequest) -> ExportResponse:
    """Packages the reproduction capsule into a .scopelet archive."""
    try:
        res = default_service.export(
            session_id=session_id,
            output_path=req.output_path,
            auto_approve=req.auto_approve,
        )
        return ExportResponse(**res)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.post("/sessions/{session_id}/verify", response_model=VerifyResponse)
def verify_session(session_id: str, req: VerifyRequest) -> VerifyResponse:
    """Verifies a candidate fix patch against private hidden regression suites."""
    try:
        res = default_service.verify(
            session_id=session_id,
            solution_patch=req.solution_patch,
            target_cmd=req.target_cmd,
            hidden_regression_cmd=req.hidden_regression_cmd,
            full_suite_cmd=req.full_suite_cmd,
        )
        return VerifyResponse(**res)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/sessions/{session_id}/report", response_model=ReportResponse)
def get_session_report(session_id: str) -> ReportResponse:
    """Generates the privacy and minimization summary report."""
    try:
        res = default_service.get_report(session_id=session_id)
        return ReportResponse(**res)
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
