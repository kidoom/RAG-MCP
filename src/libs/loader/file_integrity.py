"""SHA256-based ingestion integrity checker with SQLite persistence."""

from __future__ import annotations

import hashlib
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "db" / "ingestion_history.db"


class FileIntegrityChecker(ABC):
    """Abstract interface for ingestion file integrity tracking."""

    @abstractmethod
    def compute_sha256(self, path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def should_skip(self, file_hash: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def mark_success(self, file_hash: str, file_path: str, message: str = "") -> None:
        raise NotImplementedError

    @abstractmethod
    def mark_failed(self, file_hash: str, file_path: str, error_msg: str) -> None:
        raise NotImplementedError


class SQLiteIntegrityChecker(FileIntegrityChecker):
    """SQLite-backed checker for deduping unchanged ingested files."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_history (
                    file_hash TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    processed_at TEXT NOT NULL,
                    error_msg TEXT NOT NULL DEFAULT ''
                )
                """
            )

    def compute_sha256(self, path: str) -> str:
        fp = Path(path)
        if not fp.is_file():
            raise FileNotFoundError(f"File not found for sha256: {fp}")
        h = hashlib.sha256()
        with fp.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def should_skip(self, file_hash: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT status
                FROM ingestion_history
                WHERE file_hash = ?
                """,
                (file_hash,),
            ).fetchone()
        return bool(row and row[0] == "success")

    def mark_success(self, file_hash: str, file_path: str, message: str = "") -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_history(file_hash, file_path, status, processed_at, error_msg)
                VALUES (?, ?, 'success', ?, ?)
                ON CONFLICT(file_hash) DO UPDATE SET
                    file_path=excluded.file_path,
                    status=excluded.status,
                    processed_at=excluded.processed_at,
                    error_msg=excluded.error_msg
                """,
                (file_hash, file_path, now, message),
            )

    def mark_failed(self, file_hash: str, file_path: str, error_msg: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO ingestion_history(file_hash, file_path, status, processed_at, error_msg)
                VALUES (?, ?, 'failed', ?, ?)
                ON CONFLICT(file_hash) DO UPDATE SET
                    file_path=excluded.file_path,
                    status=excluded.status,
                    processed_at=excluded.processed_at,
                    error_msg=excluded.error_msg
                """,
                (file_hash, file_path, now, error_msg),
            )
