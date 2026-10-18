"""
Unit and integration tests for Phase 10 Behavior-Preserving Sanitizer.
Verifies AST identifier renaming, syntax validation, failure oracle checks and private mapping security.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scopelet.privacy.sanitizer.renamer import ASTRenamer
from scopelet.privacy.sanitizer.typescript_validator import TypeScriptValidator
from scopelet.privacy.sanitizer.oracle_check import OracleCheck, OracleCheckResult
from scopelet.privacy.sanitizer.mapping import MappingStore
from scopelet.privacy.sanitizer.sanitizer import BehaviorPreservingSanitizer
from scopelet.runner.result import ExecutionResult


def make_result(
    exit_code: int = 1,
    fingerprint: Optional[str] = None,
    stdout: str = "",
    stderr: str = "",
) -> ExecutionResult:
    return ExecutionResult(
        command="npm test",
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=100,
        backend="local_sandbox",
        tree_hash="hash123",
        fingerprint=fingerprint,
    )


def test_ast_renamer_identifiers_and_shorthand():
    renamer = ASTRenamer()
    source = b"""
    import { CUSTOMER_PROJECT_NEBULA } from './nebula';
    // CUSTOMER_PROJECT_NEBULA in a comment must remain untouched
    const CUSTOMER_PROJECT_NEBULA_EXTENDED = 100;
    class CUSTOMER_PROJECT_NEBULA {
        prop: string;
        constructor(val: string) {
            this.prop = val;
        }
    }
    const payload = { CUSTOMER_PROJECT_NEBULA };
    """
    modified, count = renamer.rename_in_bytes(
        source,
        "CUSTOMER_PROJECT_NEBULA",
        "customer_A",
        is_tsx=False,
        rename_strings=False,
    )

    result_str = modified.decode("utf-8")
    assert count == 3
    assert "customer_A" in result_str
    # Comment preserved exactly
    assert "// CUSTOMER_PROJECT_NEBULA in a comment must remain untouched" in result_str
    # Substring in other identifier preserved
    assert "CUSTOMER_PROJECT_NEBULA_EXTENDED = 100;" in result_str
    # Object shorthand renamed
    assert "{ customer_A }" in result_str


def test_ast_renamer_rename_strings():
    renamer = ASTRenamer()
    source = b'const name = "CANARY_TOKEN_XYZ"; const num = 42;'
    modified, count = renamer.rename_in_bytes(
        source,
        "CANARY_TOKEN_XYZ",
        "canary_token_1",
        rename_strings=True,
    )
    assert count == 1
    assert b'"canary_token_1"' in modified


def test_typescript_validator_detects_syntax_errors():
    validator = TypeScriptValidator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        bad_file = root / "broken.ts"
        bad_file.write_text("function broken( { return 42; }", encoding="utf-8")

        valid, err = validator.validate_syntax(root)
        assert valid is False
        assert "Syntax error detected" in err


def test_typescript_validator_passes_valid_code():
    validator = TypeScriptValidator()
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        good_file = root / "valid.ts"
        good_file.write_text(
            "export function add(a: number, b: number): number { return a + b; }",
            encoding="utf-8",
        )

        valid, err = validator.validate_syntax(root)
        assert valid is True
        assert err is None


def test_oracle_check_matching_fingerprint():
    mock_runner = MagicMock()
    mock_runner.run.return_value = make_result(
        exit_code=1,
        stdout="FAIL test",
        stderr="Error",
        fingerprint="fp_abc123456789",
    )

    oracle = OracleCheck(
        command="npm test",
        expected_fingerprint="fp_abc123456789",
        runner=mock_runner,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        res = oracle.verify(Path(tmp_dir))
        assert res.is_valid is True
        assert res.actual_fingerprint == "fp_abc123456789"
        assert "fingerprint preserved" in res.message


def test_oracle_check_mismatched_fingerprint():
    mock_runner = MagicMock()
    mock_runner.run.return_value = make_result(
        exit_code=1,
        stdout="FAIL test",
        stderr="Error",
        fingerprint="fp_different_000",
    )

    oracle = OracleCheck(
        command="npm test",
        expected_fingerprint="fp_expected_111",
        runner=mock_runner,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        res = oracle.verify(Path(tmp_dir))
        assert res.is_valid is False
        assert "Fingerprint mismatch" in res.message


def test_oracle_check_unexpected_pass():
    mock_runner = MagicMock()
    mock_runner.run.return_value = make_result(
        exit_code=0,
        stdout="PASS",
        stderr="",
        fingerprint=None,
    )

    oracle = OracleCheck(
        command="npm test",
        expected_fingerprint="fp_expected_111",
        runner=mock_runner,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        res = oracle.verify(Path(tmp_dir))
        assert res.is_valid is False
        assert "succeeded without failure" in res.message


def test_mapping_store_lifecycle_and_exclusion():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        store = MappingStore.for_workspace(root)
        store.add_mapping("CUSTOMER_PROJECT_NEBULA", "customer_A")
        store.add_mapping("GoldmanPricingModel", "PricingModel_A")

        saved_path = store.save(capsule_hash="hash_123")
        assert saved_path.exists()
        assert saved_path == root / ".scopelet" / "private" / "mapping.json"

        # Verify safe capsule path checks
        assert MappingStore.is_safe_capsule_path("src/index.ts") is True
        assert MappingStore.is_safe_capsule_path(".scopelet/private/mapping.json") is False
        assert MappingStore.is_safe_capsule_path(".scopelet/private/secrets.txt") is False

        # Load back
        new_store = MappingStore.for_workspace(root)
        loaded = new_store.load()
        assert loaded["CUSTOMER_PROJECT_NEBULA"] == "customer_A"
        assert new_store.get_original("PricingModel_A") == "GoldmanPricingModel"
        assert new_store.capsule_hash == "hash_123"


def test_sanitizer_preserves_and_records_safe_rename():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src_file = root / "service.ts"
        src_file.write_text(
            "export const CUSTOMER_PROJECT_NEBULA = 'active';\n"
            "export function run() { return CUSTOMER_PROJECT_NEBULA; }\n",
            encoding="utf-8",
        )

        mock_runner = MagicMock()
        mock_runner.run.return_value = make_result(
            exit_code=1,
            fingerprint="fp_target_999",
        )

        sanitizer = BehaviorPreservingSanitizer(
            workspace_dir=root,
            command="npm test",
            expected_fingerprint="fp_target_999",
            runner=mock_runner,
            strict_type_check=False,
        )

        success, msg = sanitizer.sanitize_identifier("CUSTOMER_PROJECT_NEBULA", "customer_A")
        assert success is True
        assert "fingerprint preserved" in msg

        content = src_file.read_text(encoding="utf-8")
        assert "CUSTOMER_PROJECT_NEBULA" not in content
        assert "customer_A" in content
        assert sanitizer.mapping_store.get_sanitized("CUSTOMER_PROJECT_NEBULA") == "customer_A"


def test_sanitizer_rejects_and_rolls_back_when_oracle_mismatches():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src_file = root / "service.ts"
        original_content = (
            "export const CUSTOMER_PROJECT_ORION = 'secret_data';\n"
            "export function compute() { return CUSTOMER_PROJECT_ORION; }\n"
        )
        src_file.write_text(original_content, encoding="utf-8")

        mock_runner = MagicMock()
        # Oracle returns different fingerprint because the rename broke defect reproduction
        mock_runner.run.return_value = make_result(
            exit_code=1,
            fingerprint="fp_broken_drift_888",
        )

        sanitizer = BehaviorPreservingSanitizer(
            workspace_dir=root,
            command="npm test",
            expected_fingerprint="fp_target_expected",
            runner=mock_runner,
            strict_type_check=False,
        )

        success, msg = sanitizer.sanitize_identifier("CUSTOMER_PROJECT_ORION", "customer_B")
        assert success is False
        assert "Oracle rejected" in msg

        # Rollback check: original file content is completely restored
        assert src_file.read_text(encoding="utf-8") == original_content
        # Mapping not added
        assert sanitizer.mapping_store.get_sanitized("CUSTOMER_PROJECT_ORION") is None


def test_sanitizer_auto_discovery_and_sanitization():
    with tempfile.TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        src = root / "src"
        src.mkdir()
        (src / "app.ts").write_text(
            "const CUSTOMER_PROJECT_ALPHA = 10;\n"
            "const CANARY_SECRET_TOKEN = 'seed';\n",
            encoding="utf-8",
        )

        mock_runner = MagicMock()
        mock_runner.run.return_value = make_result(
            exit_code=1,
            fingerprint="fp_constant_123",
        )

        sanitizer = BehaviorPreservingSanitizer(
            workspace_dir=root,
            command="npm test",
            expected_fingerprint="fp_constant_123",
            runner=mock_runner,
            strict_type_check=False,
        )

        mapping_store = sanitizer.auto_sanitize(capsule_hash="capsule_abc")
        assert "CUSTOMER_PROJECT_ALPHA" in mapping_store.mapping
        assert "CANARY_SECRET_TOKEN" in mapping_store.mapping

        final_content = (src / "app.ts").read_text(encoding="utf-8")
        assert "CUSTOMER_PROJECT_ALPHA" not in final_content
        assert "CANARY_SECRET_TOKEN" not in final_content
        assert (root / ".scopelet" / "private" / "mapping.json").exists()
