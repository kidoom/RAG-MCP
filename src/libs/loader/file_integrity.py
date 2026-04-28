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

# “内容哈希 + 历史状态”机制：

# 用 SHA256 表示“文件内容指纹”
# 在 SQLite 里记录这个指纹的处理状态（success/failed）
# 下次看到同 hash 且 status=success 就直接 skip


# FileIntegrityChecker 类定义了文件完整性检查的抽象接口，包括计算 SHA256 哈希、检查是否跳过、标记成功和失败。
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

    @abstractmethod
    def remove_record(self, file_hash: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_processed(self) -> list:
        raise NotImplementedError


# SQLiteIntegrityChecker 类实现了 SQLite 作为持久化存储的文件完整性检查器。它继承自 FileIntegrityChecker 抽象基类，并实现了具体的文件处理逻辑。
class SQLiteIntegrityChecker(FileIntegrityChecker):
    """SQLite-backed checker for deduping unchanged ingested files."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
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

    def remove_record(self, file_hash: str) -> bool:
        """Delete a record from ingestion_history. Returns True if removed."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM ingestion_history WHERE file_hash = ?",
                (file_hash,),
            )
            return cursor.rowcount > 0

    def list_processed(self) -> list:
        """List all processed files from ingestion_history."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT file_hash, file_path, status, processed_at, error_msg
                FROM ingestion_history
                ORDER BY processed_at DESC
                """
            ).fetchall()
        return [
            {
                "file_hash": row["file_hash"],
                "file_path": row["file_path"],
                "status": row["status"],
                "processed_at": row["processed_at"],
                "error_msg": row["error_msg"],
            }
            for row in rows
        ]
