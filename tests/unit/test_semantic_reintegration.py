"""
Unit tests for Semantic Patch Reintegration V2 (Phase 17).
Validates handling of line offset drift, whitespace drift and multi-hunk re-anchoring.
"""

from pathlib import Path
import pytest

from scopelet.reintegration import (
    ReverseIdentifierMapper,
    SemanticPatchApplierV2,
    SemanticReintegrationResult,
)


def test_semantic_applier_exact_match(tmp_path: Path):
    target_file = tmp_path / "calc.py"
    target_file.write_text(
        "def add(a, b):\n"
        "    return a - b\n"
        "\n"
        "def sub(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )

    patch_content = (
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -1,4 +1,4 @@\n"
        " def add(a, b):\n"
        "-    return a - b\n"
        "+    return a + b\n"
        " \n"
    )

    applier = SemanticPatchApplierV2(repo_dir=tmp_path)
    result = applier.apply(patch_content, target_dir=tmp_path)

    assert result.success is True
    assert "calc.py" in result.modified_files
    assert result.drift_detected is False
    assert result.confidence_score == 1.0

    updated = target_file.read_text(encoding="utf-8")
    assert "return a + b" in updated
    assert "def sub(a, b):" in updated


def test_semantic_applier_line_offset_drift(tmp_path: Path):
    """
    Simulates private repo evolution: 10 lines of comments were added at the top,
    causing the hunk's line numbers in the patch (line 2) to drift to line 12.
    """
    header_padding = "".join([f"# Header comment line {i}\n" for i in range(10)])
    target_file = tmp_path / "service.py"
    target_file.write_text(
        header_padding +
        "def compute_tax(amount):\n"
        "    rate = 0.05\n"
        "    return amount * 0.10\n"
        "\n"
        "def print_receipt():\n"
        "    pass\n",
        encoding="utf-8",
    )

    # Patch was created against older code where compute_tax was at line 1
    drifted_patch = (
        "--- a/service.py\n"
        "+++ b/service.py\n"
        "@@ -1,4 +1,4 @@\n"
        " def compute_tax(amount):\n"
        "     rate = 0.05\n"
        "-    return amount * 0.10\n"
        "+    return amount * rate\n"
        " \n"
    )

    applier = SemanticPatchApplierV2(repo_dir=tmp_path)
    result = applier.apply(drifted_patch, target_dir=tmp_path)

    assert result.success is True
    assert "service.py" in result.modified_files
    assert result.drift_detected is True
    assert result.hunks_adapted >= 1
    assert result.confidence_score >= 0.90

    updated = target_file.read_text(encoding="utf-8")
    assert "return amount * rate" in updated
    assert "# Header comment line 0" in updated
    assert "# Header comment line 9" in updated
    assert "def print_receipt():" in updated


def test_semantic_applier_whitespace_context_drift(tmp_path: Path):
    """
    Context lines in private repo had minor whitespace adjustments.
    Fuzzy anchor matching aligns and applies the replacement.
    """
    target_file = tmp_path / "formatter.py"
    target_file.write_text(
        "class  Formatter:\n"
        "    def format_row(self, val):\n"
        "        # process\n"
        "        return val.strip()\n",
        encoding="utf-8",
    )

    # Patch with slightly different spacing in context line
    patch_content = (
        "--- a/formatter.py\n"
        "+++ b/formatter.py\n"
        "@@ -1,4 +1,4 @@\n"
        "class Formatter:\n"
        "    def format_row(self, val):\n"
        "        # process\n"
        "-        return val.strip()\n"
        "+        return str(val).strip()\n"
    )

    applier = SemanticPatchApplierV2(repo_dir=tmp_path, fuzzy_threshold=0.60)
    result = applier.apply(patch_content, target_dir=tmp_path)

    assert result.success is True
    assert "formatter.py" in result.modified_files
    assert result.drift_detected is True
    assert "return str(val).strip()" in target_file.read_text(encoding="utf-8")


def test_semantic_applier_with_identifier_un_sanitization(tmp_path: Path):
    """
    Combines reverse identifier mapping with drifted line numbers.
    """
    padding = "".join([f"# Note {i}\n" for i in range(5)])
    target_file = tmp_path / "auth.py"
    target_file.write_text(
        padding +
        "def verify_token(secret_key, token):\n"
        "    return token == 'bad'\n",
        encoding="utf-8",
    )

    # Patch uses sanitized identifiers 'masked_token' and 'masked_key'
    mapping = {
        "secret_key": "masked_key",
        "token": "masked_token",
    }

    sanitized_patch = (
        "--- a/auth.py\n"
        "+++ b/auth.py\n"
        "@@ -1,2 +1,2 @@\n"
        " def verify_token(masked_key, masked_token):\n"
        "-    return masked_token == 'bad'\n"
        "+    return masked_token == masked_key\n"
    )

    applier = SemanticPatchApplierV2(repo_dir=tmp_path, mapping=mapping)
    result = applier.apply(sanitized_patch, target_dir=tmp_path)

    assert result.success is True
    assert "auth.py" in result.modified_files
    assert "secret_key" in result.un_sanitized_patch
    assert "masked_key" not in result.un_sanitized_patch

    content = target_file.read_text(encoding="utf-8")
    assert "return token == secret_key" in content


def test_semantic_applier_custom_adapter_fallback(tmp_path: Path):
    target_file = tmp_path / "complex.py"
    target_file.write_text(
        "completely different content that cannot match any context lines at all",
        encoding="utf-8",
    )

    patch_content = (
        "--- a/complex.py\n"
        "+++ b/complex.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-foo\n"
        "+bar\n"
    )

    def dummy_adapter(full_source: str, before_chunk: str, after_chunk: str) -> str:
        return "adapted by custom AI adapter"

    applier = SemanticPatchApplierV2(
        repo_dir=tmp_path,
        semantic_adapter=dummy_adapter,
        fuzzy_threshold=0.99,
    )
    result = applier.apply(patch_content, target_dir=tmp_path)

    assert result.success is True
    assert "adapted by custom AI adapter" in target_file.read_text(encoding="utf-8")
    assert any("adapted via semantic AI adapter" in d for d in result.details)


def test_semantic_applier_failure_returns_error(tmp_path: Path):
    target_file = tmp_path / "broken.py"
    target_file.write_text("irrelevant data", encoding="utf-8")

    patch_content = (
        "--- a/broken.py\n"
        "+++ b/broken.py\n"
        "@@ -10,3 +10,3 @@\n"
        " some nonexistent context\n"
        "-bad\n"
        "+good\n"
    )

    applier = SemanticPatchApplierV2(repo_dir=tmp_path)
    result = applier.apply(patch_content, target_dir=tmp_path)

    assert result.success is False
    assert result.error is not None
    assert "Could not anchor hunk" in result.error
