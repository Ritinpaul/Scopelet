"""
Private identifier mapping storage.
Stores bidirectional pseudonymization mappings in `.scopelet/private/mapping.json`.
Strictly ensures that mapping tables are owner-side only and never bundled into exported capsules.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field

DEFAULT_SCHEMA_VERSION = "1.0"


class MappingDocument(BaseModel):
    """Schema for private identifier mappings."""
    schema_version: str = DEFAULT_SCHEMA_VERSION
    mapping: Dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    capsule_hash: Optional[str] = None


class MappingStore:
    """
    Manages private mapping storage between sensitive identifiers and sanitized pseudonyms.
    """

    def __init__(self, private_dir: Optional[Path] = None):
        self.private_dir = private_dir
        self.mapping: Dict[str, str] = {}
        self.reverse_mapping: Dict[str, str] = {}
        self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.capsule_hash: Optional[str] = None

    @classmethod
    def for_workspace(cls, workspace_dir: Path) -> MappingStore:
        """Constructs a MappingStore located at workspace/.scopelet/private."""
        p_dir = workspace_dir.resolve() / ".scopelet" / "private"
        return cls(private_dir=p_dir)

    def add_mapping(self, original: str, sanitized: str) -> None:
        """Registers a bidirectional mapping."""
        self.mapping[original] = sanitized
        self.reverse_mapping[sanitized] = original

    def get_sanitized(self, original: str) -> Optional[str]:
        """Retrieves the sanitized name for an original identifier."""
        return self.mapping.get(original)

    def get_original(self, sanitized: str) -> Optional[str]:
        """Retrieves the original sensitive identifier from a sanitized name."""
        return self.reverse_mapping.get(sanitized)

    def save(self, target_path: Optional[Path] = None, capsule_hash: Optional[str] = None) -> Path:
        """
        Saves mapping data to disk.
        Defaults to self.private_dir / "mapping.json".
        """
        if target_path:
            save_file = target_path.resolve()
        elif self.private_dir:
            save_file = self.private_dir / "mapping.json"
        else:
            raise ValueError("No private directory or target path configured for MappingStore")

        save_file.parent.mkdir(parents=True, exist_ok=True)
        if capsule_hash:
            self.capsule_hash = capsule_hash

        doc = MappingDocument(
            schema_version=DEFAULT_SCHEMA_VERSION,
            mapping=self.mapping,
            created_at=self.created_at,
            capsule_hash=self.capsule_hash,
        )

        save_file.write_text(json.dumps(doc.model_dump(), indent=2), encoding="utf-8")
        return save_file

    def load(self, source_path: Optional[Path] = None) -> Dict[str, str]:
        """
        Loads mapping from disk.
        """
        load_file = source_path or (self.private_dir / "mapping.json" if self.private_dir else None)
        if not load_file or not load_file.exists():
            return {}

        data = json.loads(load_file.read_text(encoding="utf-8"))
        self.mapping = data.get("mapping", {})
        self.reverse_mapping = {v: k for k, v in self.mapping.items()}
        self.created_at = data.get("created_at", self.created_at)
        self.capsule_hash = data.get("capsule_hash", self.capsule_hash)
        return self.mapping

    @staticmethod
    def is_safe_capsule_path(rel_path: str) -> bool:
        """
        Verifies whether a relative path is safe for inclusion in an exported capsule.
        Strictly excludes private mappings and confidential keys.
        """
        normalized = rel_path.replace("\\", "/").strip("/").lower()
        parts = normalized.split("/")

        if "private" in parts or "mapping.json" in parts:
            return False

        if any(part in (".git", ".gitconfig", ".gitmodules") for part in parts):
            return False

        return True
