"""
Boundary and security policy checks for candidate patches.
Ensures patches do not tamper with tests, build configurations, or introduce dangerous operations.
"""

from __future__ import annotations

import fnmatch
from abc import ABC, abstractmethod
from pathlib import Path
import re
from typing import List, Optional

from .verdict import PolicyResult
from ..verification.patcher import PatchApplier


class BasePolicy(ABC):
    """
    Abstract base class for patch boundary and security policies.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the policy."""
        pass

    @abstractmethod
    def evaluate(
        self,
        patch_content: str,
        modified_files: List[str],
        allowed_changes: Optional[List[str]] = None,
    ) -> PolicyResult:
        """Evaluates compliance with this policy."""
        pass


class TestTamperingPolicy(BasePolicy):
    """
    Rejects patches that modify test files or disable test suites.
    """

    TEST_PATTERNS = [
        "*.test.*",
        "*.spec.*",
        "*_test.py",
        "test_*.py",
        "*/tests/*",
        "tests/*",
        "*/__tests__/*",
        "__tests__/*",
    ]

    SKIP_REGEX = re.compile(
        r"^\+\s*.*(?:\btest\.skip\b|\bdescribe\.skip\b|\bit\.skip\b|@pytest\.mark\.skip|\bunittest\.skip\b)",
        re.MULTILINE,
    )

    @property
    def name(self) -> str:
        return "Test Tampering Policy"

    def evaluate(
        self,
        patch_content: str,
        modified_files: List[str],
        allowed_changes: Optional[List[str]] = None,
    ) -> PolicyResult:
        # 1. Check if modified files contain test files
        tampered_files = []
        for f in modified_files:
            norm_f = f.replace("\\", "/")
            for pat in self.TEST_PATTERNS:
                if fnmatch.fnmatch(norm_f, pat) or fnmatch.fnmatch(Path(norm_f).name, pat):
                    tampered_files.append(norm_f)
                    break

        if tampered_files:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Unauthorized modification of test files: {', '.join(tampered_files)}",
                severity="CRITICAL",
            )

        # 2. Check if test skip annotations were injected
        if self.SKIP_REGEX.search(patch_content):
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details="Test skipping directives (e.g. test.skip or @pytest.mark.skip) detected in patch",
                severity="CRITICAL",
            )

        return PolicyResult(
            policy_name=self.name,
            passed=True,
            details="No test file tampering or test skip directives detected",
            severity="CRITICAL",
        )


class ConfigurationIntegrityPolicy(BasePolicy):
    """
    Rejects patches that modify package managers, lockfiles, or core environment configs.
    """

    FORBIDDEN_FILES = {
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "poetry.lock",
        "requirements.txt",
        "pipfile",
        "pipfile.lock",
        "dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        ".env",
        ".env.production",
        ".env.local",
        "tsconfig.json",
    }

    @property
    def name(self) -> str:
        return "Configuration Integrity Policy"

    def evaluate(
        self,
        patch_content: str,
        modified_files: List[str],
        allowed_changes: Optional[List[str]] = None,
    ) -> PolicyResult:
        tampered = []
        for f in modified_files:
            norm = f.replace("\\", "/")
            if ".." in norm.split("/") or norm.startswith("/") or norm.startswith(".."):
                tampered.append(f)
            base_name = Path(f).name.lower()
            if base_name in self.FORBIDDEN_FILES:
                tampered.append(f)

        if tampered:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Forbidden build/configuration files modified: {', '.join(tampered)}",
                severity="CRITICAL",
            )

        return PolicyResult(
            policy_name=self.name,
            passed=True,
            details="Build and dependency configuration files remain intact",
            severity="CRITICAL",
        )


class NetworkSecurityPolicy(BasePolicy):
    """
    Rejects patches that introduce outbound network communication or sockets.
    """

    NETWORK_PATTERNS = [
        re.compile(r"^\+\s*.*(?:\bfetch\s*\(|\baxios\b|http\.get|http\.post|https\.request)", re.MULTILINE),
        re.compile(r"^\+\s*.*(?:\brequests\.get\b|\brequests\.post\b|\burllib\.request\b)", re.MULTILINE),
        re.compile(r"^\+\s*.*(?:\bsocket\.socket\b|\bnet\.connect\b|\bWebSocket\b|\bXMLHttpRequest\b)", re.MULTILINE),
    ]

    @property
    def name(self) -> str:
        return "Network Security Policy"

    def evaluate(
        self,
        patch_content: str,
        modified_files: List[str],
        allowed_changes: Optional[List[str]] = None,
    ) -> PolicyResult:
        violations = []
        for pat in self.NETWORK_PATTERNS:
            match = pat.search(patch_content)
            if match:
                violations.append(match.group(0).strip())

        if violations:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Outbound network calls introduced in patch diff: {'; '.join(violations)}",
                severity="CRITICAL",
            )

        return PolicyResult(
            policy_name=self.name,
            passed=True,
            details="Zero unauthorized network calls detected in patch diff",
            severity="CRITICAL",
        )


class CodeExecutionPolicy(BasePolicy):
    """
    Rejects patches that introduce dangerous dynamic code evaluation or shell subprocesses.
    """

    EXEC_PATTERNS = [
        re.compile(r"^\+\s*.*(?:\beval\s*\(|\bexec\s*\(|\bnew Function\s*\()", re.MULTILINE),
        re.compile(r"^\+\s*.*(?:\bchild_process\b|\bsubprocess\.|\bos\.system\s*\(|\bos\.popen\s*\()", re.MULTILINE),
        re.compile(r"^\+\s*.*(?:\bprocess\.exit\b|\bsys\.exit\b)", re.MULTILINE),
    ]

    @property
    def name(self) -> str:
        return "Arbitrary Code Execution Policy"

    def evaluate(
        self,
        patch_content: str,
        modified_files: List[str],
        allowed_changes: Optional[List[str]] = None,
    ) -> PolicyResult:
        violations = []
        for pat in self.EXEC_PATTERNS:
            match = pat.search(patch_content)
            if match:
                violations.append(match.group(0).strip())

        if violations:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Dynamic evaluation or shell execution detected: {'; '.join(violations)}",
                severity="CRITICAL",
            )

        return PolicyResult(
            policy_name=self.name,
            passed=True,
            details="No dangerous dynamic code evaluation or subprocess invocations introduced",
            severity="CRITICAL",
        )


class DiffSizePolicy(BasePolicy):
    """
    Rejects patches that exceed reasonable line and file bounds for focused bug fixes.
    """

    def __init__(self, max_lines: int = 500, max_files: int = 10):
        self.max_lines = max_lines
        self.max_files = max_files

    @property
    def name(self) -> str:
        return "Diff Size Policy"

    def evaluate(
        self,
        patch_content: str,
        modified_files: List[str],
        allowed_changes: Optional[List[str]] = None,
    ) -> PolicyResult:
        if len(modified_files) > self.max_files:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Diff modifies {len(modified_files)} files, exceeding limit of {self.max_files}",
                severity="CRITICAL",
            )

        lines_changed = sum(
            1 for line in patch_content.splitlines()
            if line.startswith("+") and not line.startswith("+++") or line.startswith("-") and not line.startswith("---")
        )

        if lines_changed > self.max_lines:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Diff contains {lines_changed} changed lines, exceeding maximum limit of {self.max_lines}",
                severity="CRITICAL",
            )

        return PolicyResult(
            policy_name=self.name,
            passed=True,
            details=f"Diff size within boundaries ({len(modified_files)} files, {lines_changed} lines changed)",
            severity="CRITICAL",
        )


class AllowedFilesPolicy(BasePolicy):
    """
    Ensures patch modifications strictly adhere to manifest allowed_changes.
    """

    @property
    def name(self) -> str:
        return "Allowed Files Policy"

    def evaluate(
        self,
        patch_content: str,
        modified_files: List[str],
        allowed_changes: Optional[List[str]] = None,
    ) -> PolicyResult:
        if not allowed_changes:
            return PolicyResult(
                policy_name=self.name,
                passed=True,
                details="No file boundary restrictions specified",
                severity="CRITICAL",
            )

        allowed_set = {f.replace("\\", "/") for f in allowed_changes}
        unauthorized = [f for f in modified_files if f.replace("\\", "/") not in allowed_set]

        if unauthorized:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Modifications outside allowed_changes: {', '.join(unauthorized)}",
                severity="CRITICAL",
            )

        return PolicyResult(
            policy_name=self.name,
            passed=True,
            details="All modifications strictly within allowed_changes",
            severity="CRITICAL",
        )


class PolicyChecker:
    """
    Orchestrates all boundary and security policy evaluations.
    """

    def __init__(self, policies: Optional[List[BasePolicy]] = None):
        self.policies = policies or [
            TestTamperingPolicy(),
            ConfigurationIntegrityPolicy(),
            NetworkSecurityPolicy(),
            CodeExecutionPolicy(),
            DiffSizePolicy(),
            AllowedFilesPolicy(),
        ]

    def evaluate_all(
        self,
        patch_content: str,
        allowed_changes: Optional[List[str]] = None,
    ) -> List[PolicyResult]:
        """
        Runs all policies against patch content and returns individual results.
        """
        modified_files = PatchApplier.extract_modified_files(patch_content)
        results: List[PolicyResult] = []

        for policy in self.policies:
            res = policy.evaluate(patch_content, modified_files, allowed_changes=allowed_changes)
            results.append(res)

        return results
