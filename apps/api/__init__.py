"""
FastAPI application package for Scopelet (Phase 28).
"""

from .app import app
from .service import SessionService, default_service

__all__ = ["app", "SessionService", "default_service"]
