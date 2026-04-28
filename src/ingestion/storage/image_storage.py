"""Image file persistence with SQLite index mapping (C13)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.settings import REPO_ROOT

DEFAULT_IMAGE_ROOT = REPO_ROOT / "data" / "images"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "db" / "image_index.db"


class ImageStorage:
    """Store images on disk and maintain image_id -> path index in SQLite."""

    def __init__(
        self,
        image_root: Optional[str] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self.image_root = Path(image_root) if image_root else DEFAULT_IMAGE_ROOT
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.image_root.mkdir(parents=True, exist_ok=True)
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
                CREATE TABLE IF NOT EXISTS image_index (
                    image_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    collection TEXT,
                    doc_hash TEXT,
                    page_num INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_collection ON image_index(collection)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_hash ON image_index(doc_hash)")

    def save_image(
        self,
        image_id: str,
        image_bytes: bytes,
        *,
        collection: str,
        doc_hash: str = "",
        page_num: Optional[int] = None,
        extension: str = ".png",
    ) -> str:
        """Persist image bytes and upsert index row."""
        image_id_norm = image_id.strip()
        collection_norm = collection.strip()
        if not image_id_norm:
            raise ValueError("image_id must be a non-empty string")
        if not collection_norm:
            raise ValueError("collection must be a non-empty string")
        if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
            raise ValueError("image_bytes must be non-empty bytes")

        ext = extension if extension.startswith(".") else f".{extension}"
        target_dir = self.image_root / collection_norm
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{image_id_norm}{ext}"
        file_path.write_bytes(bytes(image_bytes))
        file_path_str = str(file_path.resolve())

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO image_index(image_id, file_path, collection, doc_hash, page_num)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(image_id) DO UPDATE SET
                    file_path=excluded.file_path,
                    collection=excluded.collection,
                    doc_hash=excluded.doc_hash,
                    page_num=excluded.page_num
                """,
                (image_id_norm, file_path_str, collection_norm, doc_hash, page_num),
            )
        return file_path_str

    def get_image_path(self, image_id: str) -> Optional[str]:
        """Get persisted file path by image_id."""
        image_id_norm = image_id.strip()
        if not image_id_norm:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT file_path FROM image_index WHERE image_id = ?",
                (image_id_norm,),
            ).fetchone()
        if row is None:
            return None
        return str(row["file_path"])

    def list_images(
        self,
        collection: str,
        doc_hash: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List indexed images by collection, optionally filtered by doc_hash."""
        collection_norm = collection.strip()
        if not collection_norm:
            raise ValueError("collection must be a non-empty string")

        sql = """
            SELECT image_id, file_path, collection, doc_hash, page_num, created_at
            FROM image_index
            WHERE collection = ?
        """
        params: List[Any] = [collection_norm]
        if doc_hash is not None:
            sql += " AND doc_hash = ?"
            params.append(doc_hash)
        sql += " ORDER BY created_at ASC, image_id ASC"

        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            {
                "image_id": str(row["image_id"]),
                "file_path": str(row["file_path"]),
                "collection": str(row["collection"]) if row["collection"] is not None else "",
                "doc_hash": str(row["doc_hash"]) if row["doc_hash"] is not None else "",
                "page_num": int(row["page_num"]) if row["page_num"] is not None else None,
                "created_at": str(row["created_at"]),
            }
            for row in rows
        ]

    def delete_images(self, collection: str, doc_hash: str) -> int:
        """Delete indexed image files and rows for one collection + document."""
        collection_norm = collection.strip()
        doc_hash_norm = doc_hash.strip()
        if not collection_norm:
            raise ValueError("collection must be a non-empty string")
        if not doc_hash_norm:
            raise ValueError("doc_hash must be a non-empty string")

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT image_id, file_path
                FROM image_index
                WHERE collection = ? AND doc_hash = ?
                """,
                (collection_norm, doc_hash_norm),
            ).fetchall()

            for row in rows:
                file_path = Path(str(row["file_path"]))
                try:
                    file_path.unlink(missing_ok=True)
                except OSError:
                    # Keep database cleanup robust even if one file is already missing/locked.
                    pass

            conn.execute(
                "DELETE FROM image_index WHERE collection = ? AND doc_hash = ?",
                (collection_norm, doc_hash_norm),
            )
        return len(rows)
