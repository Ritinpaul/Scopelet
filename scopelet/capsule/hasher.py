"""
Deterministic hashing engine for Scopelet capsules.
Produces an invariant SHA-256 hash over sorted files, content hashes, and execution metadata.
"""

from __future__ import annotations

import hashlib
from typing import List, Optional, Dict
from .models import CapsuleFile


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

    # Hash all files sorted by path
    for cf in sorted(files, key=lambda f: f.path):
        hasher.update(cf.path.encode("utf-8"))
        hasher.update(cf.hash.encode("utf-8"))
        hasher.update(str(cf.size_bytes).encode("utf-8"))

    return hasher.hexdigest()
