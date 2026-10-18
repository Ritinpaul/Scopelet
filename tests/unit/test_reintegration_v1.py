"""
Unit tests for Reintegration Engine V1 (Phase 16).
"""

from pathlib import Path
import pytest

from scopelet.reintegration.mapper import ReverseIdentifierMapper
from scopelet.reintegration.worktree import IsolatedWorktree
from scopelet.reintegration.applier import ReintegrationApplierV1


def test_reverse_identifier_mapper():
    mapping = {
        "PROJECT_NEBULA": "customer_A",
        "GoldmanPricingModel": "PricingModel_A",
    }
    mapper = ReverseIdentifierMapper(mapping)

    patch_content = (
        "--- a/src/pricing.ts\n"
        "+++ b/src/pricing.ts\n"
        "@@ -1,3 +1,3 @@\n"
        "-const model = new PricingModel_A(customer_A);\n"
        "+const model = new PricingModel_A(customer_A, true);\n"
    )

    un_sanitized = mapper.un_sanitize_patch(patch_content)
    assert "GoldmanPricingModel" in un_sanitized
    assert "PROJECT_NEBULA" in un_sanitized
    assert "PricingModel_A" not in un_sanitized
    assert "customer_A" not in un_sanitized


def test_isolated_worktree(tmp_path: Path):
    repo = tmp_path / "original_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "index.ts").write_text("console.log('original');\n", encoding="utf-8")

    with IsolatedWorktree(repo, prefer_git_worktree=False) as wt:
        assert wt.exists()
        assert (wt / "src" / "index.ts").exists()

        # Modify file inside worktree
        (wt / "src" / "index.ts").write_text("console.log('modified in worktree');\n", encoding="utf-8")
        assert (wt / "src" / "index.ts").read_text(encoding="utf-8") == "console.log('modified in worktree');\n"

        # Original repo must remain unchanged
        assert (repo / "src" / "index.ts").read_text(encoding="utf-8") == "console.log('original');\n"

    # Worktree should be cleaned up
    assert not wt.exists()


def test_reintegration_applier_v1_clean_application(tmp_path: Path):
    repo = tmp_path / "private_repo"
    repo.mkdir()
    (repo / "src").mkdir()
    target_file = repo / "src" / "pricing.ts"
    target_file.write_text("export const client = 'PROJECT_NEBULA';\n", encoding="utf-8")

    mapping = {
        "PROJECT_NEBULA": "customer_A",
    }

    # Patch from external solver using sanitized identifier
    sanitized_patch = (
        "--- a/src/pricing.ts\n"
        "+++ b/src/pricing.ts\n"
        "@@ -1 +1 @@\n"
        "-export const client = 'customer_A';\n"
        "+export const client = 'customer_A' + '_v2';\n"
    )

    applier = ReintegrationApplierV1(repo_dir=repo, mapping=mapping)
    result = applier.apply(sanitized_patch)

    assert result.success is True
    assert result.modified_files == ["src/pricing.ts"]
    assert "PROJECT_NEBULA" in result.un_sanitized_patch
    assert target_file.read_text(encoding="utf-8") == "export const client = 'PROJECT_NEBULA' + '_v2';\n"


def test_reintegration_applier_v1_failure_reports_drift(tmp_path: Path):
    repo = tmp_path / "repo_missing_file"
    repo.mkdir()

    patch_text = (
        "--- a/src/nonexistent.ts\n"
        "+++ b/src/nonexistent.ts\n"
        "@@ -1 +1 @@\n"
        "-const a = 1;\n"
        "+const a = 2;\n"
    )

    applier = ReintegrationApplierV1(repo_dir=repo, mapping={})
    result = applier.apply(patch_text)

    assert result.success is False
    assert "V1 patch application failed" in (result.error or "")
