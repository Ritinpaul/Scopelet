"""
Scopelet Ingestion and Private Verification Engine.
Validates patch integrity, checks boundary compliance and executes isolated test verdicts.
"""

from .models import TestRunVerdict, VerificationReport
from .patcher import PatchApplier, PatchError
from .engine import VerificationEngine

__all__ = [
    "TestRunVerdict",
    "VerificationReport",
    "PatchApplier",
    "PatchError",
    "VerificationEngine",
]
