"""Unit tests for DocumentManager (G2)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from ingestion.document_manager import (
    CollectionStats,
    DeleteResult,
    DocumentInfo,
    DocumentManager,
)


class _FakeChromaStore:
    """In-memory fake for ChromaStore used by DocumentManager tests."""

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    def upsert(self, records, trace=None) -> None:
        for r in records:
            self._records.append({
                "id": r.id,
                "text": r.text,
                "metadata": dict(r.metadata),
            })

    def get_by_metadata(self, filters, trace=None) -> List[Dict[str, Any]]:
        out = []
        for r in self._records:
            match = True
            for k, v in (filters or {}).items():
                if r.get("metadata", {}).get(k) != v:
                    match = False
                    break
            if match:
                out.append(r)
        return out

    def get_by_ids(self, ids, trace=None) -> List[Dict[str, Any]]:
        return [r for r in self._records if r["id"] in ids]

    def delete_by_metadata(self, filters, trace=None) -> int:
        before = len(self._records)
        self._records = [
            r for r in self._records
            if any(r.get("metadata", {}).get(k) != v for k, v in (filters or {}).items())
        ]
        return before - len(self._records)

    def get_collection_stats(self, trace=None) -> Dict[str, Any]:
        return {"collection_name": "test", "entry_count": len(self._records)}

    def get_all_collections(self) -> List[str]:
        return ["test", "other"]


class _FakeBM25:
    """In-memory fake for BM25Indexer."""

    def __init__(self) -> None:
        self._doc_terms: Dict[str, Dict[str, int]] = {}
        self._doc_lengths: Dict[str, int] = {}
        self._doc_count = 0
        self._inverted_index: Dict[str, Any] = {}

    @property
    def doc_count(self) -> int:
        return self._doc_count

    def load(self) -> bool:
        self._doc_count = len(self._doc_terms)
        return True

    def remove_document(self, chunk_id: str) -> bool:
        if chunk_id in self._doc_terms:
            del self._doc_terms[chunk_id]
            self._doc_lengths.pop(chunk_id, None)
            self._doc_count = len(self._doc_terms)
            return True
        return False

    def remove_documents(self, chunk_ids: List[str]) -> int:
        removed = 0
        for cid in chunk_ids:
            if cid in self._doc_terms:
                del self._doc_terms[cid]
                self._doc_lengths.pop(cid, None)
                removed += 1
        self._doc_count = len(self._doc_terms)
        return removed


class _FakeImages:
    """In-memory fake for ImageStorage."""

    def __init__(self) -> None:
        self._images: List[Dict[str, Any]] = []

    def save_image(self, image_id, image_bytes, *, collection, doc_hash="", page_num=None, extension=".png"):
        self._images.append({
            "image_id": image_id,
            "file_path": f"/fake/{collection}/{doc_hash}/{image_id}{extension}",
            "collection": collection,
            "doc_hash": doc_hash,
        })

    def list_images(self, collection, doc_hash=None):
        return [
            img for img in self._images
            if img["collection"] == collection
            and (doc_hash is None or img["doc_hash"] == doc_hash)
        ]

    def delete_images(self, collection, doc_hash) -> int:
        before = len(self._images)
        self._images = [
            img for img in self._images
            if not (img["collection"] == collection and img["doc_hash"] == doc_hash)
        ]
        return before - len(self._images)


class _FakeIntegrity:
    """In-memory fake for FileIntegrityChecker."""

    def __init__(self) -> None:
        self._records: List[Dict[str, Any]] = []

    def compute_sha256(self, path) -> str:
        return "hash_" + Path(path).name

    def should_skip(self, file_hash) -> bool:
        return any(r["file_hash"] == file_hash and r["status"] == "success" for r in self._records)

    def mark_success(self, file_hash, file_path, message="") -> None:
        self._records.append({
            "file_hash": file_hash,
            "file_path": file_path,
            "status": "success",
            "processed_at": "2026-01-15T00:00:00Z",
            "error_msg": message,
        })

    def mark_failed(self, file_hash, file_path, error_msg) -> None:
        self._records.append({
            "file_hash": file_hash,
            "file_path": file_path,
            "status": "failed",
            "processed_at": "2026-01-15T00:00:00Z",
            "error_msg": error_msg,
        })

    def remove_record(self, file_hash) -> bool:
        before = len(self._records)
        self._records = [r for r in self._records if r["file_hash"] != file_hash]
        return len(self._records) < before

    def list_processed(self):
        return list(self._records)


@pytest.fixture
def fake_doc_manager():
    """DocumentManager wired with in-memory fakes."""
    chroma = _FakeChromaStore()
    bm25 = _FakeBM25()
    images = _FakeImages()
    integrity = _FakeIntegrity()
    return DocumentManager(
        chroma_store=chroma,
        bm25_indexer=bm25,
        image_storage=images,
        integrity_checker=integrity,
    ), chroma, bm25, images, integrity


class TestDocumentManager:
    """Tests for DocumentManager contract."""

    def test_list_documents_empty(self, fake_doc_manager):
        mgr, _, _, _, _ = fake_doc_manager
        docs = mgr.list_documents()
        assert docs == []

    def test_list_documents_with_data(self, fake_doc_manager):
        mgr, chroma, _, _, integrity = fake_doc_manager

        # Populate chroma with records
        from libs.vector_store.base_vector_store import VectorRecord
        chroma.upsert([
            VectorRecord(
                id="chunk_1",
                vector=[0.1, 0.2],
                text="hello",
                metadata={"source_path": "/data/doc1.pdf", "collection": "test"},
            ),
            VectorRecord(
                id="chunk_2",
                vector=[0.3, 0.4],
                text="world",
                metadata={"source_path": "/data/doc1.pdf", "collection": "test"},
            ),
            VectorRecord(
                id="chunk_3",
                vector=[0.5, 0.6],
                text="foo",
                metadata={"source_path": "/data/doc2.pdf", "collection": "test"},
            ),
        ])
        integrity.mark_success("hash1", "/data/doc1.pdf", "ok")

        docs = mgr.list_documents()
        assert len(docs) >= 1

    def test_get_document_detail_found(self, fake_doc_manager):
        mgr, chroma, _, _, _ = fake_doc_manager

        from libs.vector_store.base_vector_store import VectorRecord
        chroma.upsert([
            VectorRecord(
                id="chunk_1",
                vector=[0.1, 0.2],
                text="content",
                metadata={"source_path": "/data/doc.pdf", "collection": "test"},
            ),
        ])

        detail = mgr.get_document_detail("/data/doc.pdf", collection="test")
        assert detail is not None
        assert detail.collection == "test"
        assert len(detail.chunks) >= 1

    def test_get_document_detail_not_found(self, fake_doc_manager):
        mgr, _, _, _, _ = fake_doc_manager
        detail = mgr.get_document_detail("nonexistent")
        assert detail is None

    def test_delete_document(self, fake_doc_manager):
        mgr, chroma, bm25, images, integrity = fake_doc_manager

        from libs.vector_store.base_vector_store import VectorRecord
        chroma.upsert([
            VectorRecord(
                id="chunk_1",
                vector=[0.1, 0.2],
                text="content",
                metadata={"source_path": "/data/doc.pdf"},
            ),
        ])
        integrity.mark_success("hash_doc", "/data/doc.pdf", "doc_id=abc123;chunks=1")
        bm25._doc_terms["chunk_1"] = {"hello": 1}
        bm25._doc_count = 1
        images.save_image(
            "img1", b"fakebytes",
            collection="knowledge_hub",
            doc_hash="abc123",
        )

        result = mgr.delete_document("/data/doc.pdf")
        assert result.success or result.chroma_deleted > 0

    def test_delete_document_empty(self, fake_doc_manager):
        mgr, _, _, _, _ = fake_doc_manager
        result = mgr.delete_document("nonexistent.pdf")
        assert result.success is False

    def test_get_collection_stats(self, fake_doc_manager):
        mgr, chroma, bm25, images, integrity = fake_doc_manager

        from libs.vector_store.base_vector_store import VectorRecord
        chroma.upsert([
            VectorRecord(
                id="chunk_1",
                vector=[0.1, 0.2],
                text="content",
                metadata={"source_path": "/data/doc.pdf"},
            ),
        ])
        bm25._doc_terms["chunk_1"] = {"hello": 1}
        bm25._doc_count = 1
        integrity.mark_success("hash1", "/data/doc.pdf", "ok")

        stats = mgr.get_collection_stats()
        assert isinstance(stats, CollectionStats)
        assert stats.chroma_entries >= 0
