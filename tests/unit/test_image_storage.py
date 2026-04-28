"""Unit tests for ImageStorage (C13)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ingestion.storage import ImageStorage


def _make_storage(tmp_path: Path) -> ImageStorage:
    return ImageStorage(
        image_root=str(tmp_path / "images"),
        db_path=str(tmp_path / "db" / "image_index.db"),
    )


def test_image_storage_save_and_lookup_path(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    out_path = storage.save_image(
        "img-001",
        b"fake-image-bytes",
        collection="kb-a",
        doc_hash="doc-a",
        page_num=2,
        extension=".jpg",
    )

    file_path = Path(out_path)
    assert file_path.exists()
    assert file_path.read_bytes() == b"fake-image-bytes"
    assert storage.get_image_path("img-001") == out_path


def test_image_storage_mapping_persists_in_sqlite(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    out_path = storage.save_image("img-002", b"abc", collection="kb-a", doc_hash="doc-b")

    reopened = _make_storage(tmp_path)
    assert reopened.get_image_path("img-002") == out_path

    db_file = tmp_path / "db" / "image_index.db"
    assert db_file.exists()
    with sqlite3.connect(str(db_file)) as conn:
        row = conn.execute(
            "SELECT image_id, file_path, collection, doc_hash FROM image_index WHERE image_id = ?",
            ("img-002",),
        ).fetchone()
    assert row is not None
    assert row[0] == "img-002"
    assert row[1] == out_path
    assert row[2] == "kb-a"
    assert row[3] == "doc-b"


def test_image_storage_list_images_by_collection_and_doc_hash(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    storage.save_image("img-a1", b"a1", collection="kb-a", doc_hash="doc-1")
    storage.save_image("img-a2", b"a2", collection="kb-a", doc_hash="doc-2")
    storage.save_image("img-b1", b"b1", collection="kb-b", doc_hash="doc-1")

    list_a = storage.list_images("kb-a")
    assert [item["image_id"] for item in list_a] == ["img-a1", "img-a2"]

    only_doc_2 = storage.list_images("kb-a", doc_hash="doc-2")
    assert [item["image_id"] for item in only_doc_2] == ["img-a2"]


def test_image_storage_delete_images_removes_file_and_index(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)
    p1 = Path(storage.save_image("img-del-1", b"d1", collection="kb-a", doc_hash="doc-x"))
    p2 = Path(storage.save_image("img-del-2", b"d2", collection="kb-a", doc_hash="doc-x"))
    storage.save_image("img-keep", b"k", collection="kb-a", doc_hash="doc-y")

    deleted = storage.delete_images("kb-a", "doc-x")
    assert deleted == 2
    assert not p1.exists()
    assert not p2.exists()
    assert storage.get_image_path("img-del-1") is None
    assert [x["image_id"] for x in storage.list_images("kb-a")] == ["img-keep"]


def test_image_storage_validates_required_inputs(tmp_path: Path) -> None:
    storage = _make_storage(tmp_path)

    with pytest.raises(ValueError, match="image_id"):
        storage.save_image("", b"abc", collection="kb")
    with pytest.raises(ValueError, match="collection"):
        storage.save_image("img", b"abc", collection="")
    with pytest.raises(ValueError, match="image_bytes"):
        storage.save_image("img", b"", collection="kb")
    with pytest.raises(ValueError, match="collection"):
        storage.list_images("")
    with pytest.raises(ValueError, match="doc_hash"):
        storage.delete_images("kb", "")
