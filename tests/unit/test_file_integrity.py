from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.libs.loader import SQLiteIntegrityChecker


def test_compute_sha256_is_deterministic(tmp_path: Path):
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    checker = SQLiteIntegrityChecker(db_path=str(tmp_path / "history.db"))

    h1 = checker.compute_sha256(str(f))
    h2 = checker.compute_sha256(str(f))

    assert h1 == h2
    assert len(h1) == 64


def test_mark_success_enables_skip(tmp_path: Path):
    db = tmp_path / "history.db"
    checker = SQLiteIntegrityChecker(db_path=str(db))
    file_hash = "a" * 64

    assert checker.should_skip(file_hash) is False
    checker.mark_success(file_hash, "data/documents/a.pdf")
    assert checker.should_skip(file_hash) is True


def test_mark_failed_does_not_enable_skip(tmp_path: Path):
    checker = SQLiteIntegrityChecker(db_path=str(tmp_path / "history.db"))
    file_hash = "b" * 64

    checker.mark_failed(file_hash, "data/documents/b.pdf", "parse failed")

    assert checker.should_skip(file_hash) is False


def test_database_file_is_created(tmp_path: Path):
    db = tmp_path / "db" / "ingestion_history.db"
    SQLiteIntegrityChecker(db_path=str(db))
    assert db.exists()


def test_sqlite_uses_wal_mode(tmp_path: Path):
    db = tmp_path / "history.db"
    checker = SQLiteIntegrityChecker(db_path=str(db))

    with sqlite3.connect(str(checker.db_path)) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]

    assert journal_mode.lower() == "wal"


def test_concurrent_mark_success_writes(tmp_path: Path):
    db = tmp_path / "history.db"
    checker = SQLiteIntegrityChecker(db_path=str(db))

    def _worker(i: int):
        h = f"{i:064x}"[-64:]
        checker.mark_success(h, f"data/documents/{i}.pdf")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_worker, range(50)))

    for i in range(50):
        h = f"{i:064x}"[-64:]
        assert checker.should_skip(h) is True
