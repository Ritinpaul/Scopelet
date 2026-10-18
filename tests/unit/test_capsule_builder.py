"""
Unit tests for Scopelet capsule builder, packager, hasher, and manifest schema validation.
"""

import json
import tempfile
import zipfile
from pathlib import Path
import pytest
import yaml

from scopelet.capsule.models import CapsuleFile, CapsuleManifest, TaskSpec
from scopelet.capsule.hasher import compute_capsule_hash
from scopelet.capsule.packager import CapsulePackager, SecurityError
from scopelet.capsule.builder import CapsuleBuilder
from scopelet.reducer.candidate import CandidateState


def test_capsule_manifest_schema_validation():
    manifest = CapsuleManifest(
        schema_version="1.0",
        capsule_hash="abc123hash",
        title="Sample invoice timezone error",
        created_at="2026-10-18T00:30:00Z",
        runtime={"node": "22"},
        command="npm test",
        allowed_changes=["src/date.ts"],
        expected={"test_should_pass": True},
        network_allowed=False,
        failure_fingerprint="fp_123456",
        files=[CapsuleFile(path="src/date.ts", hash="hash1", size_bytes=100)],
    )

    data = manifest.model_dump()
    assert data["schema_version"] == "1.0"
    assert data["capsule_hash"] == "abc123hash"
    assert data["runtime"]["node"] == "22"
    assert len(data["files"]) == 1

    # Verify JSON schema exists and validates
    schema_path = Path("schemas/capsule.schema.json")
    assert schema_path.exists()
    schema_dict = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "properties" in schema_dict


def test_capsule_hasher_determinism_and_order_invariance():
    f1 = CapsuleFile(path="src/b.ts", hash="hash_b", size_bytes=20)
    f2 = CapsuleFile(path="src/a.ts", hash="hash_a", size_bytes=10)

    # Order invariance
    h1 = compute_capsule_hash([f1, f2], command="npm test")
    h2 = compute_capsule_hash([f2, f1], command="npm test")
    assert h1 == h2
    assert len(h1) == 64

    # Sensitivity
    h3 = compute_capsule_hash([f1], command="npm test")
    assert h1 != h3


def test_capsule_packager_pack_and_unpack(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "package.json").write_text("{}", encoding="utf-8")
    (source / "src").mkdir()
    (source / "src" / "index.ts").write_text("console.log('test');", encoding="utf-8")

    archive = tmp_path / "test.scopelet"
    CapsulePackager.pack(source, archive)
    assert archive.exists()
    assert archive.stat().st_size > 0

    dest = tmp_path / "unpacked"
    CapsulePackager.unpack(archive, dest)

    assert (dest / "package.json").exists()
    assert (dest / "src" / "index.ts").exists()
    assert (dest / "src" / "index.ts").read_text(encoding="utf-8") == "console.log('test');"


def test_capsule_packager_zip_slip_protection(tmp_path: Path):
    """Verifies that malicious zip entries with directory traversal paths are rejected."""
    bad_zip = tmp_path / "malicious.scopelet"

    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0:")

    target_dir = tmp_path / "safe_extract"
    with pytest.raises(SecurityError, match="Directory traversal"):
        CapsulePackager.unpack(bad_zip, target_dir)


def test_capsule_builder_assembles_manifest_and_specs(tmp_path: Path):
    repo = tmp_path / "reduced_repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"name": "capsule-test"}', encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "calculator.ts").write_text("export function add() { return 1; }", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "calc.test.ts").write_text("it('adds', () => {});", encoding="utf-8")

    state = CandidateState.from_directory(repo)

    out_dir = tmp_path / "assembled_capsule"
    builder = CapsuleBuilder()
    manifest = builder.build(
        output_dir=out_dir,
        state=state,
        title="Add operation bug",
        command="npm test",
        failure_fingerprint="fp_synthetic_123",
        allowed_changes=["src/calculator.ts"],
    )

    assert (out_dir / "capsule.json").exists()
    assert (out_dir / "task.yaml").exists()
    assert (out_dir / "README.md").exists()
    assert (out_dir / "src" / "calculator.ts").exists()

    # Verify task.yaml
    task_content = yaml.safe_load((out_dir / "task.yaml").read_text(encoding="utf-8"))
    assert task_content["title"] == "Add operation bug"
    assert task_content["command"] == "npm test"
    assert task_content["allowed_changes"] == ["src/calculator.ts"]

    # Verify capsule.json
    manifest_loaded = json.loads((out_dir / "capsule.json").read_text(encoding="utf-8"))
    assert manifest_loaded["capsule_hash"] == manifest.capsule_hash
    assert manifest_loaded["failure_fingerprint"] == "fp_synthetic_123"
