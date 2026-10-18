"""
Integration tests for Phase 28 FastAPI service layer and REST endpoints.
Validates all 9 REST endpoints using TestClient.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from apps.api.app import app
from apps.api.service import SessionService, default_service
from scopelet.capsule.builder import CapsuleBuilder
from scopelet.reducer.candidate import CandidateState

client = TestClient(app)


def test_api_create_and_get_session(tmp_path):
    """Validates POST /sessions and GET /sessions/{id}."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "index.ts").write_text("console.log('hi');", encoding="utf-8")
    (repo_dir / "package.json").write_text('{"name": "test"}', encoding="utf-8")

    # 1. Create session
    resp = client.post(
        "/sessions",
        json={"repo_dir": str(repo_dir), "title": "Test API Session"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    assert data["title"] == "Test API Session"
    assert data["status"] == "initialized"
    session_id = data["session_id"]

    # 2. Retrieve session
    get_resp = client.get(f"/sessions/{session_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["session_id"] == session_id
    assert get_data["title"] == "Test API Session"


def test_api_get_nonexistent_session_404():
    """Validates that querying a non-existent session ID returns 404."""
    resp = client.get("/sessions/nonexistent-uuid-12345")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_api_capture_endpoint(tmp_path, monkeypatch):
    """Validates POST /sessions/{id}/capture."""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "test.ts").write_text("console.log('test');", encoding="utf-8")

    session = default_service.create_session(str(repo_dir), title="Capture Test")
    session_id = session.session_id

    mock_capture_res = {
        "session_id": session_id,
        "fingerprint": "fp_mock_capture_123",
        "test_name": "Invoice calculation test",
        "exception": "AssertionError: Expected 100 but got 99",
        "exit_code": 1,
        "duration_ms": 150,
        "stack_frames": ["src/math.ts:10"],
    }
    monkeypatch.setattr(default_service, "capture", lambda **kw: mock_capture_res)

    resp = client.post(
        f"/sessions/{session_id}/capture",
        json={"command": "npm test", "timeout": 60},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["fingerprint"] == "fp_mock_capture_123"
    assert data["test_name"] == "Invoice calculation test"


def test_api_analyze_endpoint(monkeypatch):
    """Validates POST /sessions/{id}/analyze."""
    session = default_service.create_session(".", title="Analyze Test")
    session_id = session.session_id

    mock_analyze_res = {
        "session_id": session_id,
        "total_nodes": 12,
        "slice_files": ["src/index.ts", "src/utils.ts"],
        "dynamic_coverage_count": 2,
    }
    monkeypatch.setattr(default_service, "analyze", lambda **kw: mock_analyze_res)

    resp = client.post(f"/sessions/{session_id}/analyze")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_nodes"] == 12
    assert "src/utils.ts" in data["slice_files"]


def test_api_reduce_endpoint(monkeypatch):
    """Validates POST /sessions/{id}/reduce."""
    session = default_service.create_session(".", title="Reduce Test")
    session_id = session.session_id

    mock_reduce_res = {
        "session_id": session_id,
        "initial_files": 20,
        "final_files": 3,
        "evaluations": 14,
        "cache_hits": 4,
        "kept_files": ["src/a.ts", "src/b.ts", "package.json"],
        "reduction_percentage": 85.0,
    }
    monkeypatch.setattr(default_service, "reduce", lambda **kw: mock_reduce_res)

    resp = client.post(
        f"/sessions/{session_id}/reduce",
        json={"max_evaluations": 30, "enable_ai_ranker": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_files"] == 3
    assert data["reduction_percentage"] == 85.0


def test_api_sanitize_endpoint(monkeypatch):
    """Validates POST /sessions/{id}/sanitize."""
    session = default_service.create_session(".", title="Sanitize Test")
    session_id = session.session_id

    mock_sanitize_res = {
        "session_id": session_id,
        "sanitized": True,
        "replacements_count": 5,
        "fingerprint_preserved": True,
    }
    monkeypatch.setattr(default_service, "sanitize", lambda **kw: mock_sanitize_res)

    resp = client.post(f"/sessions/{session_id}/sanitize")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sanitized"] is True
    assert data["replacements_count"] == 5


def test_api_export_endpoint(monkeypatch):
    """Validates POST /sessions/{id}/export."""
    session = default_service.create_session(".", title="Export Test")
    session_id = session.session_id

    mock_export_res = {
        "session_id": session_id,
        "archive_path": "reproduction.scopelet",
        "capsule_hash": "sha256_mock_hash_abc123",
        "file_size_bytes": 1024,
    }
    monkeypatch.setattr(default_service, "export", lambda **kw: mock_export_res)

    resp = client.post(
        f"/sessions/{session_id}/export",
        json={"output_path": "reproduction.scopelet", "auto_approve": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["capsule_hash"] == "sha256_mock_hash_abc123"


def test_api_verify_endpoint(monkeypatch):
    """Validates POST /sessions/{id}/verify."""
    session = default_service.create_session(".", title="Verify Test")
    session_id = session.session_id

    mock_verify_res = {
        "session_id": session_id,
        "verdict": "ACCEPT",
        "patch_hash": "hash_patch_123",
        "target_test_passed": True,
        "hidden_regression_passed": True,
        "rejection_reasons": [],
        "duration_ms": 250,
    }
    monkeypatch.setattr(default_service, "verify", lambda **kw: mock_verify_res)

    resp = client.post(
        f"/sessions/{session_id}/verify",
        json={"solution_patch": "--- a/test.ts\n+++ b/test.ts\n@@ -1 +1 @@\n-1\n+2\n"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "ACCEPT"
    assert data["target_test_passed"] is True


def test_api_report_endpoint(monkeypatch):
    """Validates GET /sessions/{id}/report."""
    session = default_service.create_session(".", title="Report Test")
    session_id = session.session_id

    mock_report_res = {
        "session_id": session_id,
        "title": "Report Test",
        "original_files": 25,
        "original_loc": 1000,
        "capsule_files": 3,
        "capsule_loc": 120,
        "reduction_pct": 88.0,
        "secret_findings_count": 0,
        "canaries_found": 0,
        "manual_review_status": "APPROVED",
    }
    monkeypatch.setattr(default_service, "get_report", lambda **kw: mock_report_res)

    resp = client.get(f"/sessions/{session_id}/report")
    assert resp.status_code == 200
    data = resp.json()
    assert data["reduction_pct"] == 88.0
    assert data["manual_review_status"] == "APPROVED"
