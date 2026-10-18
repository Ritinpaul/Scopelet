"""
SQLite-backed deterministic execution cache.
Prevents redundant re-execution of identical candidate trees during reduction and testing.
"""

import hashlib
import sqlite3
import datetime
from pathlib import Path
from typing import Optional, List
from .result import ExecutionResult

DEFAULT_IGNORE_DIRS = {
    "node_modules",
    ".git",
    ".scopelet",
    "dist",
    ".pytest_cache",
    "__pycache__",
    ".vitest",
    "build",
}


def compute_tree_hash(directory: Path, ignore_dirs: Optional[set[str]] = None) -> str:
    """
    Computes a deterministic SHA-256 hash over all regular files in a directory tree.
    Files are sorted by relative path to guarantee order invariance.
    """
    ignored = ignore_dirs or DEFAULT_IGNORE_DIRS
    hasher = hashlib.sha256()

    all_files: List[Path] = []
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            # Check if any parent part is in ignored
            rel_parts = p.relative_to(directory).parts
            if any(part in ignored for part in rel_parts):
                continue
            all_files.append(p)

    for file_path in all_files:
        rel_path = file_path.relative_to(directory).as_posix().encode("utf-8")
        hasher.update(rel_path)
        try:
            content = file_path.read_bytes()
            hasher.update(content)
        except (OSError, PermissionError):
            pass

    return hasher.hexdigest()


class ExecutionCache:
    """
    Persistent SQLite cache keyed by SHA256(tree_hash + command + env_hash + backend).
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    cache_key TEXT PRIMARY KEY,
                    tree_hash TEXT NOT NULL,
                    command TEXT NOT NULL,
                    env_hash TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    stdout TEXT NOT NULL,
                    stderr TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    fingerprint TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.commit()

    @staticmethod
    def make_cache_key(tree_hash: str, command: str, env_hash: str, backend: str) -> str:
        raw = f"{tree_hash}:{command}:{env_hash}:{backend}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get(
        self,
        tree_hash: str,
        command: str,
        env_hash: str = "default",
        backend: str = "local_sandbox",
    ) -> Optional[ExecutionResult]:
        key = self.make_cache_key(tree_hash, command, env_hash, backend)
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM executions WHERE cache_key = ?",
                (key,),
            )
            row = cur.fetchone()
            if row:
                return ExecutionResult(
                    schema_version="1.0",
                    command=row["command"],
                    exit_code=row["exit_code"],
                    stdout=row["stdout"],
                    stderr=row["stderr"],
                    duration_ms=row["duration_ms"],
                    backend=row["backend"],
                    tree_hash=row["tree_hash"],
                    cached=True,
                    fingerprint=row["fingerprint"],
                )
        return None

    def put(
        self,
        result: ExecutionResult,
        env_hash: str = "default",
    ) -> None:
        key = self.make_cache_key(
            result.tree_hash,
            result.command,
            env_hash,
            result.backend,
        )
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO executions (
                    cache_key, tree_hash, command, env_hash, backend,
                    exit_code, stdout, stderr, duration_ms, fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    result.tree_hash,
                    result.command,
                    env_hash,
                    result.backend,
                    result.exit_code,
                    result.stdout,
                    result.stderr,
                    result.duration_ms,
                    result.fingerprint,
                    now,
                ),
            )
            conn.commit()

    def clear(self) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM executions")
            conn.commit()

    def count(self) -> int:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM executions")
            return int(cur.fetchone()[0])
