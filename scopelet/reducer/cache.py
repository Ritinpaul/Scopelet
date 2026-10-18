"""
Persistent SQLite execution cache for delta-debugging reduction oracle evaluations.
Keyed by (tree_hash, command, env_hash) to avoid redundant candidate runs.
"""

from __future__ import annotations

import datetime
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any


class ReducerCache:
    """
    SQLite-backed cache for oracle evaluation results during reduction.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reducer_oracle_evaluations (
                    tree_hash TEXT NOT NULL,
                    command TEXT NOT NULL,
                    env_hash TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    fingerprint TEXT,
                    exit_code INTEGER NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    error_message TEXT,
                    timestamp TEXT NOT NULL,
                    PRIMARY KEY (tree_hash, command, env_hash)
                )
                """
            )
            conn.commit()

    def get(self, tree_hash: str, command: str, env_hash: str = "default") -> Optional[Dict[str, Any]]:
        """
        Retrieves cached oracle evaluation if present.
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT verdict, fingerprint, exit_code, duration_ms, error_message
                FROM reducer_oracle_evaluations
                WHERE tree_hash = ? AND command = ? AND env_hash = ?
                """,
                (tree_hash, command, env_hash),
            )
            row = cur.fetchone()
            if row:
                self.hits += 1
                return dict(row)

        self.misses += 1
        return None

    def put(
        self,
        tree_hash: str,
        command: str,
        verdict: str,
        fingerprint: Optional[str],
        exit_code: int,
        duration_ms: int,
        error_message: Optional[str] = None,
        env_hash: str = "default",
    ) -> None:
        """
        Records an oracle evaluation result.
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reducer_oracle_evaluations (
                    tree_hash, command, env_hash, verdict, fingerprint,
                    exit_code, duration_ms, error_message, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tree_hash,
                    command,
                    env_hash,
                    verdict,
                    fingerprint,
                    exit_code,
                    duration_ms,
                    error_message,
                    now,
                ),
            )
            conn.commit()

    def stats(self) -> Dict[str, int]:
        """
        Returns cache query statistics.
        """
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_queries": self.hits + self.misses,
        }
