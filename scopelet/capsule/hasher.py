"""
Deterministic hashing engine for Scopelet capsules.
Produces an invariant SHA-256 hash over sorted files, content hashes and execution metadata.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .models import CapsuleFile, CapsuleManifest


def compute_capsule_hash(
    files: List[CapsuleFile],
    command: str,
    runtime: Optional[Dict[str, str]] = None,
    allowed_changes: Optional[List[str]] = None,
) -> str:
    """
    Computes deterministic SHA-256 hash for a capsule archive.
    Files are ordered strictly by POSIX relative path.
    """
    hasher = hashlib.sha256()

    # Hash execution command
    hasher.update(command.strip().encode("utf-8"))

    # Hash runtime specification
    if runtime:
        for k in sorted(runtime.keys()):
            hasher.update(f"{k}:{runtime[k]}".encode("utf-8"))

    # Hash allowed changes list
    if allowed_changes:
        for ac in sorted(allowed_changes):
            hasher.update(ac.encode("utf-8"))

    # Hash all files sorted by POSIX path
    for cf in sorted(files, key=lambda f: f.path):
        hasher.update(cf.path.encode("utf-8"))
        hasher.update(cf.hash.encode("utf-8"))
        hasher.update(str(cf.size_bytes).encode("utf-8"))

    return hasher.hexdigest()


def verify_capsule_dir(capsule_dir: Path) -> Tuple[bool, Optional[str]]:
    """
    Verifies that all files inside a capsule directory match the manifest and that
    the capsule_hash matches the recomputed cryptographic hash.
    Returns (True, None) if valid, or (False, failure_reason).
    """
    target = capsule_dir.resolve()
    manifest_path = target / "capsule.json"
    if not manifest_path.exists():
        return False, f"Missing capsule.json in {capsule_dir}"

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = CapsuleManifest.model_validate(data)
    except Exception as exc:
        return False, f"Failed to parse capsule.json: {exc}"

    # Verify each declared file exists and has identical hash
    declared_paths = set()
    for cf in manifest.files:
        declared_paths.add(cf.path)
        file_path = target / cf.path
        if not file_path.exists():
            return False, f"Declared file missing from capsule: {cf.path}"
        actual_content = file_path.read_bytes()
        actual_hash = hashlib.sha256(actual_content).hexdigest()
        if actual_hash != cf.hash:
            return False, f"Hash mismatch for {cf.path}: expected {cf.hash}, got {actual_hash}"
        if len(actual_content) != cf.size_bytes:
            return False, f"Size mismatch for {cf.path}: expected {cf.size_bytes}, got {len(actual_content)}"

    # Recompute capsule hash
    recomputed_hash = compute_capsule_hash(
        files=manifest.files,
        command=manifest.command,
        runtime=manifest.runtime,
        allowed_changes=manifest.allowed_changes,
    )

    if recomputed_hash != manifest.capsule_hash:
        return (
            False,
            f"Capsule hash mismatch: declared {manifest.capsule_hash}, recomputed {recomputed_hash}",
        )

    return True, None


def verify_capsule_archive(archive_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Unpacks an archive into a temporary directory and verifies its contents and hash.
    """
    from .packager import CapsulePackager

    archive = archive_path.resolve()
    if not archive.exists():
        return False, f"Archive does not exist: {archive}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        try:
            CapsulePackager.unpack(archive, tmp_path)
        except Exception as exc:
            return False, f"Failed to unpack archive: {exc}"

        return verify_capsule_dir(tmp_path)
