"""
Scopelet Independent Capsule Builder and Runner.
"""

from .models import (
    CapsuleFile,
    CapsuleManifest,
    TaskSpec,
    SolutionMetadata,
    SolutionVerification,
)
from .hasher import compute_capsule_hash
from .packager import CapsulePackager, SecurityError
from .builder import CapsuleBuilder
from .runner import CapsuleRunner
from .solver import CapsuleSolver, SolverStatus
from .submission import (
    SubmissionEngine,
    SubmissionResult,
    SubmissionError,
    UnauthorizedModificationError,
    VerificationError,
)

__all__ = [
    "CapsuleFile",
    "CapsuleManifest",
    "TaskSpec",
    "SolutionMetadata",
    "SolutionVerification",
    "compute_capsule_hash",
    "CapsulePackager",
    "SecurityError",
    "CapsuleBuilder",
    "CapsuleRunner",
    "CapsuleSolver",
    "SolverStatus",
    "SubmissionEngine",
    "SubmissionResult",
    "SubmissionError",
    "UnauthorizedModificationError",
    "VerificationError",
]
