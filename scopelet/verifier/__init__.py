"""
Private Hidden Verifier package.
The definitive oracle for candidate patch verification, boundary policy enforcement,
and authoritative ACCEPT/REJECT/REVIEW verdicts.
"""

from .policies import (
    AllowedFilesPolicy,
    BasePolicy,
    CodeExecutionPolicy,
    ConfigurationIntegrityPolicy,
    DiffSizePolicy,
    NetworkSecurityPolicy,
    PolicyChecker,
    TestTamperingPolicy,
)
from .verdict import HiddenVerifierReport, PolicyResult, Verdict
from .verifier import PrivateHiddenVerifier

__all__ = [
    "Verdict",
    "PolicyResult",
    "HiddenVerifierReport",
    "PrivateHiddenVerifier",
    "PolicyChecker",
    "BasePolicy",
    "TestTamperingPolicy",
    "ConfigurationIntegrityPolicy",
    "NetworkSecurityPolicy",
    "CodeExecutionPolicy",
    "DiffSizePolicy",
    "AllowedFilesPolicy",
]
