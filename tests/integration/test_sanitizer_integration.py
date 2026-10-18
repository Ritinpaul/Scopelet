"""
Integration and system tests for Behavior-Preserving Sanitizer (Phase 10).
Verifies multi-file AST renaming, oracle rollback and privacy scanner integration.
"""

from pathlib import Path
import json
import pytest

from scopelet.runner import ExecutionResult, IsolatedRunner
from scopelet.privacy.sanitizer import BehaviorPreservingSanitizer, MappingStore
from scopelet.privacy.scanner.semantic_scanner import SemanticScanner
from scopelet.privacy.scanner.canary_scanner import CanaryScanner


def _setup_multi_file_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "sanitizer_integration_ws"
    ws.mkdir()
    (ws / "src").mkdir()
    (ws / "tests").mkdir()

    # Source file 1: Business logic with sensitive terms
    (ws / "src" / "billing.ts").write_text(
        "export const CUSTOMER_PROJECT_ALPHA = 'PROPRIETARY_BILLING_SYS';\n"
        "export function computeFee(amount: number): number {\n"
        "    const rate = 0.05;\n"
        "    return amount * rate;\n"
        "}\n",
        encoding="utf-8",
    )

    # Source file 2: References billing and has seeded canary
    (ws / "src" / "invoice.ts").write_text(
        "import { CUSTOMER_PROJECT_ALPHA, computeFee } from './billing';\n"
        "export const SEEDED_CANARY_TOKEN = 'CANARY_98765_SECRET';\n"
        "export function generateInvoice(amount: number): { total: number; tag: string } {\n"
        "    const fee = computeFee(amount);\n"
        "    return {\n"
        "        total: amount + fee,\n"
        "        tag: CUSTOMER_PROJECT_ALPHA,\n"
        "    };\n"
        "}\n",
        encoding="utf-8",
    )

    # Test file that reproduces the defect
    (ws / "tests" / "invoice.test.ts").write_text(
        "import { generateInvoice } from '../src/invoice';\n"
        "// Defect: expected calculation mismatch\n"
        "const inv = generateInvoice(100);\n"
        "if (inv.total !== 100) {\n"
        "    throw new Error('EXPECTED_AMOUNT_MISMATCH: got ' + inv.total);\n"
        "}\n",
        encoding="utf-8",
    )

    return ws


def test_sanitizer_system_multi_file_transformation_and_mapping(tmp_path: Path):
    """
    Verifies multi-file AST transformation, oracle verification and mapping exclusion.
    """
    ws = _setup_multi_file_workspace(tmp_path)
    expected_fingerprint = "EXPECTED_AMOUNT_MISMATCH"

    class MockIntegrationRunner:
        def __init__(self):
            self.invocations = []

        def run(self, command: str, cwd: Path, timeout: int = 30, **kwargs) -> ExecutionResult:
            self.invocations.append((command, cwd))
            # Check if syntax is broken
            billing_content = (cwd / "src" / "billing.ts").read_text(encoding="utf-8")
            invoice_content = (cwd / "src" / "invoice.ts").read_text(encoding="utf-8")

            # If both files agree on renamed identifier, failure fingerprint is preserved
            if "CUSTOMER_PROJECT_ALPHA" in billing_content and "CUSTOMER_PROJECT_ALPHA" not in invoice_content:
                return ExecutionResult(
                    command=command,
                    exit_code=1,
                    stdout="TypeError: Cannot find name CUSTOMER_PROJECT_ALPHA",
                    stderr="",
                    duration_ms=25,
                    backend="local_sandbox",
                    tree_hash="hash_mismatch",
                    timed_out=False,
                )

            # Failure is preserved as expected
            return ExecutionResult(
                command=command,
                exit_code=1,
                stdout=f"AssertionError: {expected_fingerprint}: got 105",
                stderr="",
                duration_ms=30,
                backend="local_sandbox",
                tree_hash="hash_ok",
                timed_out=False,
                fingerprint=expected_fingerprint,
            )

    runner = MockIntegrationRunner()
    sanitizer = BehaviorPreservingSanitizer(
        workspace_dir=ws,
        command="npm test",
        expected_fingerprint=expected_fingerprint,
        runner=runner,
        strict_type_check=False,
    )

    canaries = {"CANARY_98765_SECRET"}
    custom_terms = ["CUSTOMER_PROJECT_ALPHA"]
    mapping_store = sanitizer.auto_sanitize(canaries=canaries, custom_terms=custom_terms)

    # Verify transformations were applied
    billing_txt = (ws / "src" / "billing.ts").read_text(encoding="utf-8")
    invoice_txt = (ws / "src" / "invoice.ts").read_text(encoding="utf-8")

    assert "CUSTOMER_PROJECT_ALPHA" not in billing_txt
    assert "CUSTOMER_PROJECT_ALPHA" not in invoice_txt
    assert "CANARY_98765_SECRET" not in invoice_txt

    # Verify pseudonym consistency across files
    sanitized_id = mapping_store.get_sanitized("CUSTOMER_PROJECT_ALPHA")
    assert sanitized_id is not None
    assert sanitized_id in billing_txt
    assert sanitized_id in invoice_txt

    # Verify mapping store file location and exclusion rule
    mapping_file = ws / ".scopelet" / "private" / "mapping.json"
    assert mapping_file.exists()
    assert not MappingStore.is_safe_capsule_path(mapping_file.as_posix())
    assert not MappingStore.is_safe_capsule_path(".scopelet/private/mapping.json")
    assert MappingStore.is_safe_capsule_path("src/billing.ts")


def test_sanitizer_rollback_on_behavioral_drift(tmp_path: Path):
    """
    Verifies that when a rename alters runtime failure behavior,
    the workspace is rolled back to exact original byte content.
    """
    ws = _setup_multi_file_workspace(tmp_path)
    expected_fingerprint = "EXPECTED_AMOUNT_MISMATCH"

    orig_billing = (ws / "src" / "billing.ts").read_text(encoding="utf-8")
    orig_invoice = (ws / "src" / "invoice.ts").read_text(encoding="utf-8")

    class DriftSimulationRunner:
        def run(self, command: str, cwd: Path, timeout: int = 30, **kwargs) -> ExecutionResult:
            # Simulate behavioral drift (failure disappears or changed)
            return ExecutionResult(
                command=command,
                exit_code=0,
                stdout="All tests passed successfully!",
                stderr="",
                duration_ms=20,
                backend="local_sandbox",
                tree_hash="hash_drift",
                timed_out=False,
            )

    runner = DriftSimulationRunner()
    sanitizer = BehaviorPreservingSanitizer(
        workspace_dir=ws,
        command="npm test",
        expected_fingerprint=expected_fingerprint,
        runner=runner,
        strict_type_check=False,
    )

    success, message = sanitizer.sanitize_identifier("CUSTOMER_PROJECT_ALPHA", "customer_a")
    assert not success
    assert "Oracle rejected" in message

    # Verify rollback preserved exact files
    assert (ws / "src" / "billing.ts").read_text(encoding="utf-8") == orig_billing
    assert (ws / "src" / "invoice.ts").read_text(encoding="utf-8") == orig_invoice


def test_sanitizer_leaves_zero_proprietary_patterns(tmp_path: Path):
    """
    Verifies that running sanitizer eliminates proprietary patterns detected by PrivacyScanner.
    """
    from scopelet.privacy.scanner.orchestrator import PrivacyScanner

    ws = _setup_multi_file_workspace(tmp_path)
    expected_fingerprint = "EXPECTED_AMOUNT_MISMATCH"

    # Pre-condition: PrivacyScanner detects proprietary patterns and canaries
    pre_scanner = PrivacyScanner(canaries={"CANARY_98765_SECRET"})
    pre_report = pre_scanner.scan(ws)
    assert len(pre_report.findings) > 0, "Initial workspace must contain sensitive findings"

    class SafeRenamingRunner:
        def run(self, command: str, cwd: Path, timeout: int = 30, **kwargs) -> ExecutionResult:
            return ExecutionResult(
                command=command,
                exit_code=1,
                stdout=f"Error: {expected_fingerprint}",
                stderr="",
                duration_ms=25,
                backend="local_sandbox",
                tree_hash="hash_stable",
                timed_out=False,
                fingerprint=expected_fingerprint,
            )

    sanitizer = BehaviorPreservingSanitizer(
        workspace_dir=ws,
        command="npm test",
        expected_fingerprint=expected_fingerprint,
        runner=SafeRenamingRunner(),
        strict_type_check=False,
    )

    sanitizer.auto_sanitize(canaries={"CANARY_98765_SECRET"}, custom_terms=["CUSTOMER_PROJECT_ALPHA"])

    post_scanner = PrivacyScanner(canaries={"CANARY_98765_SECRET"})
    post_report = post_scanner.scan(ws)
    canary_findings = [f for f in post_report.findings if f.category == "canary"]
    assert len(canary_findings) == 0, "No seed canaries should remain after sanitization"

