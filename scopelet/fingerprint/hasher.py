"""
Deterministic canonical hashing for failure fingerprints.
"""

import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    """
    Serializes data to canonical JSON with sorted keys and no whitespace.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_fingerprint(data: Any) -> str:
    """
    Computes a SHA-256 fingerprint hash of canonical JSON data.
    """
    encoded = canonical_json(data).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
