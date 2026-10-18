"""
Behavior-preserving sanitizer engine for Scopelet.
Anonymizes sensitive identifiers and symbols while guaranteeing bug reproducibility.
"""

from .renamer import ASTRenamer
from .typescript_validator import TypeScriptValidator
from .oracle_check import OracleCheck, OracleCheckResult
from .mapping import MappingStore
from .sanitizer import BehaviorPreservingSanitizer

__all__ = [
    "ASTRenamer",
    "TypeScriptValidator",
    "OracleCheck",
    "OracleCheckResult",
    "MappingStore",
    "BehaviorPreservingSanitizer",
]
