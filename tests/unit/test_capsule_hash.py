"""
Unit tests for deterministic capsule hashing, bit-level reproducibility and tamper detection.
Validates requirements for Phase 22.
"""

import json
from pathlib import Path
import pytest

from scopelet.capsule.hasher import (
    compute_capsule_hash,
    verify_capsule_dir,
    verify_capsule_archive,
)
from scopelet.capsule.models import CapsuleFile
from scopelet.capsule.builder import CapsuleBuilder
from scopelet.capsule.packager import CapsulePackager
from scopelet.reducer.candidate import CandidateState


def test_capsule_hash_deterministic_across_orderings():
    """Validates that file input ordering does not alter the canonical capsule hash."""
    f1 = CapsuleFile(path="src/index.ts", hash="abc123hash", size_bytes=100)
    f2 = CapsuleFile(path="package.json", hash="def456hash", size_bytes=50)
    f3 = CapsuleFile(path="src/utils.ts", hash="789xyzhash", size_bytes=200)

    hash1 = compute_capsule_hash(
        files=[f1, f2, f3],
        command="npm test",
        runtime={"node": "22", "arch": "x64"},
        allowed_changes=["src/index.ts", "src/utils.ts"],
    )

    hash2 = compute_capsule_hash(
        files=[f3, f1, f2],  # Shuffled input order
        command="npm test",
        runtime={"arch": "x64", "node": "22"},  # Shuffled runtime keys
        allowed_changes=["src/utils.ts", "src/index.ts"],  # Shuffled allowed changes
    )

    assert hash1 == hash2


def test_capsule_hash_changes_on_content_change():
    """Validates that any byte change in a source file produces a distinct hash."""
    f1 = CapsuleFile(path="src/index.ts", hash="original_hash", size_bytes=100)
    f2 = CapsuleFile(path="package.json", hash="pkg_hash", size_bytes=50)

    hash_original = compute_capsule_hash([f1, f2], command="npm test")

    f1_modified = CapsuleFile(path="src/index.ts", hash="tampered_hash", size_bytes=100)
    hash_modified = compute_capsule_hash([f1_modified, f2], command="npm test")

    assert hash_original != hash_modified


def test_capsule_hash_changes_on_command_change():
    """Validates that modifying the reproduction command alters the hash."""
    f1 = CapsuleFile(path="src/index.ts", hash="hash1", size_bytes=100)

    h1 = compute_capsule_hash([f1], command="npm test")
    h2 = compute_capsule_hash([f1], command="npm run test:unit")

    assert h1 != h2


def test_capsule_hash_changes_on_file_addition():
    """Validates that adding an additional file changes the capsule hash."""
    f1 = CapsuleFile(path="src/index.ts", hash="hash1", size_bytes=100)
    f2 = CapsuleFile(path="src/extra.ts", hash="hash2", size_bytes=40)

    h1 = compute_capsule_hash([f1], command="npm test")
    h2 = compute_capsule_hash([f1, f2], command="npm test")

    assert h1 != h2


def test_verify_capsule_dir_success(tmp_path):
    """Validates that an assembled capsule directory passes cryptographic verification."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "src").mkdir()
    (source_dir / "src" / "index.ts").write_text("console.log('hello');", encoding="utf-8")
    (source_dir / "package.json").write_text('{"name": "test"}', encoding="utf-8")

    state = CandidateState(root_dir=source_dir, active_files={"src/index.ts", "package.json"})
    builder = CapsuleBuilder()
    capsule_dir = tmp_path / "capsule_ws"

    builder.build(
        output_dir=capsule_dir,
        state=state,
        title="Test Capsule",
        command="npm test",
        failure_fingerprint="fp12345",
    )

    is_valid, reason = verify_capsule_dir(capsule_dir)
    assert is_valid is True
    assert reason is None


def test_verify_capsule_dir_tampered_file(tmp_path):
    """Validates that tampering with a file inside a capsule fails verification."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "src").mkdir()
    (source_dir / "src" / "index.ts").write_text("console.log('clean');", encoding="utf-8")
    (source_dir / "package.json").write_text('{"name": "test"}', encoding="utf-8")

    state = CandidateState(root_dir=source_dir, active_files={"src/index.ts", "package.json"})
    builder = CapsuleBuilder()
    capsule_dir = tmp_path / "capsule_ws"

    builder.build(
        output_dir=capsule_dir,
        state=state,
        title="Tamper Test",
        command="npm test",
        failure_fingerprint="fp999",
    )

    # Tamper with the file
    (capsule_dir / "src" / "index.ts").write_text("console.log('malicious modification');", encoding="utf-8")

    is_valid, reason = verify_capsule_dir(capsule_dir)
    assert is_valid is False
    assert "Hash mismatch" in reason


def test_verify_capsule_dir_missing_file(tmp_path):
    """Validates that deleting a declared file fails verification."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "src").mkdir()
    (source_dir / "src" / "index.ts").write_text("console.log('clean');", encoding="utf-8")
    (source_dir / "package.json").write_text('{"name": "test"}', encoding="utf-8")

    state = CandidateState(root_dir=source_dir, active_files={"src/index.ts", "package.json"})
    builder = CapsuleBuilder()
    capsule_dir = tmp_path / "capsule_ws"

    builder.build(
        output_dir=capsule_dir,
        state=state,
        title="Missing File Test",
        command="npm test",
        failure_fingerprint="fp999",
    )

    # Delete declared file
    (capsule_dir / "src" / "index.ts").unlink()

    is_valid, reason = verify_capsule_dir(capsule_dir)
    assert is_valid is False
    assert "missing from capsule" in reason


def test_deterministic_archive_bit_identical(tmp_path):
    """Validates that packing the same directory twice produces bit-for-bit identical archives."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "b.txt").write_text("content B", encoding="utf-8")
    (source_dir / "a.txt").write_text("content A", encoding="utf-8")
    (source_dir / "sub").mkdir()
    (source_dir / "sub" / "c.txt").write_text("content C", encoding="utf-8")

    archive1 = tmp_path / "capsule1.scopelet"
    archive2 = tmp_path / "capsule2.scopelet"

    CapsulePackager.pack(source_dir, archive1)
    CapsulePackager.pack(source_dir, archive2)

    bytes1 = archive1.read_bytes()
    bytes2 = archive2.read_bytes()

    assert bytes1 == bytes2, "Archive generation must be bit-level reproducible"


def test_verify_capsule_archive_roundtrip(tmp_path):
    """Validates that packing and verifying an archive succeeds."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "src").mkdir()
    (source_dir / "src" / "calculator.ts").write_text("export const add = (a: number, b: number) => a + b;", encoding="utf-8")
    (source_dir / "package.json").write_text('{"name": "calc"}', encoding="utf-8")

    state = CandidateState(root_dir=source_dir, active_files={"src/calculator.ts", "package.json"})
    builder = CapsuleBuilder()
    capsule_dir = tmp_path / "capsule_ws"

    builder.build(
        output_dir=capsule_dir,
        state=state,
        title="Archive Roundtrip Test",
        command="npm test",
        failure_fingerprint="fp_calc",
    )

    archive_path = tmp_path / "test.scopelet"
    CapsulePackager.pack(capsule_dir, archive_path)

    is_valid, reason = verify_capsule_archive(archive_path)
    assert is_valid is True
    assert reason is None


def test_capsule_json_sorted_keys(tmp_path):
    """Validates that capsule.json keys are strictly sorted in alphabetical order."""
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "file.txt").write_text("data", encoding="utf-8")

    state = CandidateState(root_dir=source_dir, active_files={"file.txt"})
    builder = CapsuleBuilder()
    capsule_dir = tmp_path / "capsule_ws"

    builder.build(
        output_dir=capsule_dir,
        state=state,
        title="Sorted Keys Test",
        command="npm test",
        failure_fingerprint="fp_keys",
    )

    raw_json = (capsule_dir / "capsule.json").read_text(encoding="utf-8")
    parsed_json = json.loads(raw_json)
    keys = list(parsed_json.keys())
    assert keys == sorted(keys), "Top-level keys in capsule.json must be alphabetically sorted"
