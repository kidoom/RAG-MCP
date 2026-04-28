"""Unit tests for SparseRetriever (D3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

from core.query_engine.sparse_retriever import SparseRetriever


class FakeBM25Indexer:
    def __init__(self, hits: List[Dict[str, Any]]):
        self.hits = hits
        self.calls: List[Dict[str, Any]] = []

    def load(self) -> bool:
        return True

    def query(self, keywords: List[str], top_k: int = 10) -> List[Dict[str, Any]]:
        self.calls.append({"keywords": keywords, "top_k": top_k})
        return self.hits


class FakeVectorStore:
    def __init__(self, records: List[Dict[str, Any]]):
        self.records = records
        self.calls: List[Dict[str, Any]] = []

    def get_by_ids(self, ids: List[str], trace: Any = None) -> List[Dict[str, Any]]:
        self.calls.append({"ids": ids, "trace": trace})
        wanted = set(ids)
        return [record for record in self.records if record.get("id") in wanted]


@dataclass
class _MinimalSettings:
    vector_store: Any


def _make_settings() -> _MinimalSettings:
    vector_store = type(
        "VectorStoreCfg",
        (),
        {
            "provider": "chroma",
            "persist_directory": "./data/db/chroma",
            "collection_name": "test",
        },
    )()
    return _MinimalSettings(vector_store=vector_store)


def test_sparse_retriever_merges_bm25_hits_with_vector_records() -> None:
    bm25 = FakeBM25Indexer(
        hits=[
            {"chunk_id": "c2", "score": 2.0},
            {"chunk_id": "c1", "score": 1.2},
        ]
    )
    store = FakeVectorStore(
        records=[
            {"id": "c1", "text": "first chunk", "metadata": {"source": "a.md"}},
            {"id": "c2", "text": "second chunk", "metadata": {"source": "b.md"}},
        ]
    )
    retriever = SparseRetriever(settings=_make_settings(), bm25_indexer=bm25, vector_store=store)

    results = retriever.retrieve(keywords=["azure", "rag"], top_k=2)

    assert bm25.calls == [{"keywords": ["azure", "rag"], "top_k": 2}]
    assert store.calls == [{"ids": ["c2", "c1"], "trace": None}]
    assert [item.chunk_id for item in results] == ["c2", "c1"]
    assert results[0].text == "second chunk"
    assert results[1].metadata == {"source": "a.md"}


def test_sparse_retriever_skips_hits_missing_storage_record() -> None:
    bm25 = FakeBM25Indexer(hits=[{"chunk_id": "c_missing", "score": 1.0}])
    store = FakeVectorStore(records=[])
    retriever = SparseRetriever(settings=_make_settings(), bm25_indexer=bm25, vector_store=store)

    results = retriever.retrieve(keywords=["test"], top_k=3)

    assert results == []


def test_sparse_retriever_validates_inputs() -> None:
    retriever = SparseRetriever(
        settings=_make_settings(),
        bm25_indexer=FakeBM25Indexer(hits=[]),
        vector_store=FakeVectorStore(records=[]),
    )

    with pytest.raises(ValueError, match="top_k must be positive"):
        retriever.retrieve(keywords=["x"], top_k=0)
    assert retriever.retrieve(keywords=[], top_k=3) == []
