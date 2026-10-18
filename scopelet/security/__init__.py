"""
Security module for Scopelet.
Provides container isolation configurations, process limits and safe archive extraction.
"""

from .sandbox import (
    DOCKER_SECURITY_CONFIG,
    LOCAL_PROCESS_POLICY,
    MAX_OUTPUT_BYTES,
    SafeExtractor,
    SecurityViolationError,
    truncate_output,
    validate_docker_args,
    validate_mount,
)

__all__ = [
    "DOCKER_SECURITY_CONFIG",
    "LOCAL_PROCESS_POLICY",
    "MAX_OUTPUT_BYTES",
    "SafeExtractor",
    "SecurityViolationError",
    "truncate_output",
    "validate_docker_args",
    "validate_mount",
]
