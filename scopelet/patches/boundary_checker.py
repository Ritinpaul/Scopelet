"""
Patch Boundary Verifier Engine (Phase 15).
Enforces security rules and task constraints on external solver patches before ingestion.
"""

from __future__ import annotations

import fnmatch
from abc import ABC, abstractmethod
from pathlib import Path
import re
from typing import List, Optional
from pydantic import BaseModel, Field

from ..verification.patcher import PatchApplier


class PolicyResult(BaseModel):
    """
    Standardized result of an individual patch boundary check.
    """
    policy_name: str = Field(..., description="Name of policy check")
    passed: bool = Field(..., description="Whether diff adheres to policy")
    details: str = Field(..., description="Outcome description or violation notes")


class PolicyCheck(ABC):
    """
    Abstract base class for individual boundary policy checks.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        pass


class TestFileModificationCheck(PolicyCheck):
    """
    Rejects patches that modify test files or fixtures.
    """
    TEST_GLOBS = [
        "*.test.*",
        "*.spec.*",
        "test_*",
        "*_test.*",
        "tests/*",
        "*/tests/*",
        "__tests__/*",
        "*/__tests__/*",
    ]

    @property
    def name(self) -> str:
        return "Test File Modification"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        violating = []
        for f in files:
            norm = f.replace("\\", "/")
            base = Path(norm).name
            if any(fnmatch.fnmatch(norm, g) or fnmatch.fnmatch(base, g) for g in self.TEST_GLOBS):
                violating.append(norm)

        if violating:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Modifications to test files rejected: {', '.join(violating)}",
            )
        return PolicyResult(policy_name=self.name, passed=True, details="No test files modified")


class TestSkippingCheck(PolicyCheck):
    """
    Rejects patches that inject test skipping directives.
    """
    SKIP_RE = re.compile(
        r"^\+\s*.*(?:\btest\.skip\b|\bdescribe\.skip\b|\bit\.skip\b|@pytest\.mark\.skip|\bunittest\.skip\b)",
        re.MULTILINE,
    )

    @property
    def name(self) -> str:
        return "Test Skipping Directives"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        if self.SKIP_RE.search(diff):
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details="Diff introduces test skipping directives (e.g. test.skip)",
            )
        return PolicyResult(policy_name=self.name, passed=True, details="No test skipping directives detected")


class PackageConfigCheck(PolicyCheck):
    """
    Rejects patches that alter package manifests or lockfiles.
    """
    CONFIG_FILES = {
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
        return "Package Config Integrity"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        violating = [f for f in files if Path(f).name.lower() in self.CONFIG_FILES]
        if violating:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Modification to build/package configuration files: {', '.join(violating)}",
            )
        return PolicyResult(policy_name=self.name, passed=True, details="Package configuration files untouched")


class ForbiddenFilesCheck(PolicyCheck):
    """
    Rejects modifications to forbidden files declared in task specification.
    """

    @property
    def name(self) -> str:
        return "Forbidden Files Compliance"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        if not forbidden_files:
            return PolicyResult(policy_name=self.name, passed=True, details="No forbidden files specified")

        forbidden_set = {f.replace("\\", "/") for f in forbidden_files}
        violating = [f for f in files if f.replace("\\", "/") in forbidden_set]

        if violating:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Modified files are listed in task forbidden_files: {', '.join(violating)}",
            )
        return PolicyResult(policy_name=self.name, passed=True, details="Zero forbidden files modified")


class NetworkCallsCheck(PolicyCheck):
    """
    Rejects additions of outbound networking or sockets.
    """
    NETWORK_PATTERNS = [
        re.compile(r"^\+\s*.*(?:\bfetch\s*\(|\baxios\b|http\.get|http\.post|https\.request)", re.MULTILINE),
        re.compile(r"^\+\s*.*(?:\brequests\.get\b|\brequests\.post\b|\burllib\.request\b)", re.MULTILINE),
        re.compile(r"^\+\s*.*(?:\bsocket\.socket\b|\bnet\.connect\b|\bWebSocket\b)", re.MULTILINE),
    ]

    @property
    def name(self) -> str:
        return "Network Call Prohibition"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        found = []
        for pat in self.NETWORK_PATTERNS:
            match = pat.search(diff)
            if match:
                found.append(match.group(0).strip())

        if found:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Outbound network calls detected in diff: {'; '.join(found)}",
            )
        return PolicyResult(policy_name=self.name, passed=True, details="No unauthorized network calls added")


class ValidationDisablingCheck(PolicyCheck):
    """
    Rejects patches that delete validation checks or hardcode blanket bypasses.
    """
    BYPASS_PATTERNS = [
        re.compile(r"^\+\s*return\s+true\s*;\s*//\s*bypass", re.MULTILINE | re.IGNORECASE),
        re.compile(r"^\+\s*return\s+true\s*;\s*$", re.MULTILINE),
    ]

    @property
    def name(self) -> str:
        return "Validation Integrity"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        for pat in self.BYPASS_PATTERNS:
            if pat.search(diff):
                # Check if it was deleting an entire validation function
                return PolicyResult(
                    policy_name=self.name,
                    passed=False,
                    details="Suspicious validation bypass or unconditional return detected",
                )
        return PolicyResult(policy_name=self.name, passed=True, details="No validation bypass detected")


class ShellExecutionCheck(PolicyCheck):
    """
    Rejects dynamic code execution or subprocess invocations.
    """
    EXEC_PATTERNS = [
        re.compile(r"^\+\s*.*(?:\beval\s*\(|\bexec\s*\(|\bnew Function\s*\()", re.MULTILINE),
        re.compile(r"^\+\s*.*(?:\bchild_process\b|\bsubprocess\.|\bos\.system\s*\()", re.MULTILINE),
    ]

    @property
    def name(self) -> str:
        return "Shell and Dynamic Execution"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        found = []
        for pat in self.EXEC_PATTERNS:
            match = pat.search(diff)
            if match:
                found.append(match.group(0).strip())

        if found:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Arbitrary dynamic or shell execution detected: {'; '.join(found)}",
            )
        return PolicyResult(policy_name=self.name, passed=True, details="No shell or dynamic code execution detected")


class DependencyVersionCheck(PolicyCheck):
    """
    Rejects dependency additions or version bumps.
    """
    DEP_RE = re.compile(r"^\+\s*[\"']?[@a-zA-Z0-9_\-\./]+[\"']?\s*:\s*[\"'][\^~]?\d+", re.MULTILINE)

    @property
    def name(self) -> str:
        return "Dependency Version Lock"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        if self.DEP_RE.search(diff):
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details="Dependency version additions or updates detected in diff",
            )
        return PolicyResult(policy_name=self.name, passed=True, details="Zero dependency changes")


class DiffSizeLimitCheck(PolicyCheck):
    """
    Rejects patches that exceed size thresholds.
    """

    def __init__(self, max_lines: int = 500, max_files: int = 10):
        self.max_lines = max_lines
        self.max_files = max_files

    @property
    def name(self) -> str:
        return "Diff Size Threshold"

    def check(
        self,
        diff: str,
        files: List[str],
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> PolicyResult:
        if len(files) > self.max_files:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Modified file count ({len(files)}) exceeds maximum limit ({self.max_files})",
            )

        changed_lines = sum(
            1 for line in diff.splitlines()
            if (line.startswith("+") and not line.startswith("+++")) or (line.startswith("-") and not line.startswith("---"))
        )

        if changed_lines > self.max_lines:
            return PolicyResult(
                policy_name=self.name,
                passed=False,
                details=f"Changed line count ({changed_lines}) exceeds limit ({self.max_lines})",
            )

        return PolicyResult(
            policy_name=self.name,
            passed=True,
            details=f"Diff size acceptable ({len(files)} files, {changed_lines} lines)",
        )


class BoundaryChecker:
    """
    Evaluates unified diff patches against all boundary checks.
    """

    def __init__(self, checks: Optional[List[PolicyCheck]] = None):
        self.checks = checks or [
            TestFileModificationCheck(),
            TestSkippingCheck(),
            PackageConfigCheck(),
            ForbiddenFilesCheck(),
            NetworkCallsCheck(),
            ValidationDisablingCheck(),
            ShellExecutionCheck(),
            DependencyVersionCheck(),
            DiffSizeLimitCheck(),
        ]

    def check_all(
        self,
        diff: str,
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> List[PolicyResult]:
        files = PatchApplier.extract_modified_files(diff)
        results: List[PolicyResult] = []

        for chk in self.checks:
            res = chk.check(
                diff=diff,
                files=files,
                allowed_changes=allowed_changes,
                forbidden_files=forbidden_files,
            )
            results.append(res)

        return results

    def is_valid(
        self,
        diff: str,
        allowed_changes: Optional[List[str]] = None,
        forbidden_files: Optional[List[str]] = None,
    ) -> bool:
        results = self.check_all(diff, allowed_changes=allowed_changes, forbidden_files=forbidden_files)
        return all(r.passed for r in results)
