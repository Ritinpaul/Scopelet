"""
Capsule packaging and extraction engine with ZIP-slip protection and path normalization.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path


class SecurityError(Exception):
    """Raised when an archive contains unsafe paths or directory traversal attempts."""
    pass


class CapsulePackager:
    """
    Handles compression and decompression of .scopelet capsule archives.
    """

    @staticmethod
    def pack(source_dir: Path, output_path: Path) -> Path:
        """
        Packs source_dir into a .scopelet zip archive.
        All paths are normalized to POSIX relative paths.
        Deterministic timestamps are applied to ensure bit-level reproducible archives.
        """
        source = source_dir.resolve()
        output = output_path.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        fixed_time = (2026, 1, 1, 0, 0, 0)

        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(source.rglob("*")):
                if file_path.is_file():
                    rel_path = file_path.relative_to(source).as_posix()
                    zinfo = zipfile.ZipInfo(filename=rel_path, date_time=fixed_time)
                    zinfo.external_attr = 0o644 << 16
                    with file_path.open("rb") as f:
                        zf.writestr(zinfo, f.read())

        return output

    @staticmethod
    def unpack(archive_path: Path, target_dir: Path) -> Path:
        """
        Extracts a .scopelet archive into target_dir with strict path traversal checking.
        Prevents Zip Slip attacks.
        """
        archive = archive_path.resolve()
        target = target_dir.resolve()
        target.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(archive, "r") as zf:
            for member in zf.infolist():
                # Disallow drive letters or absolute paths
                if os.path.isabs(member.filename) or ":" in member.filename:
                    raise SecurityError(
                        f"Unsafe absolute path or drive letter in archive entry: {member.filename}"
                    )

                # Resolve path safely
                dest_path = (target / member.filename).resolve()
                if not dest_path.is_relative_to(target):
                    raise SecurityError(
                        f"Directory traversal attack detected in archive entry: {member.filename}"
                    )

                if member.is_dir():
                    dest_path.mkdir(parents=True, exist_ok=True)
                else:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src_f, dest_path.open("wb") as dst_f:
                        dst_f.write(src_f.read())

        return target
