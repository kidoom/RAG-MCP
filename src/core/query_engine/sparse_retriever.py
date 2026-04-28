"""Sparse retriever implementation for BM25-based recall (D3)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.settings import REPO_ROOT, Settings
from core.types import RetrievalResult
from ingestion.storage import BM25Indexer
from libs.vector_store import (
    BaseVectorStore,
    VectorStoreFactory,
    VectorStoreSettings as LibVectorStoreSettings,
)


class SparseRetriever:
    """Query BM25 index and enrich hits with text/metadata from vector store."""

    def __init__(
        self,
        settings: Settings,
        bm25_indexer: Optional[BM25Indexer] = None,
        vector_store: Optional[BaseVectorStore] = None,
    ) -> None:
        self._settings = settings
        self._bm25_indexer = bm25_indexer or BM25Indexer(
            index_dir=str(REPO_ROOT / "data" / "db" / "bm25")
        )
        self._bm25_indexer.load()
        self._vector_store = vector_store or VectorStoreFactory.create(
            LibVectorStoreSettings(
                provider=settings.vector_store.provider,
                persist_directory=settings.vector_store.persist_directory,
                collection_name=settings.vector_store.collection_name,
            )
        )

    def retrieve(
        self,
        keywords: List[str],
        top_k: int,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not keywords:
            return []

        bm25_hits = self._bm25_indexer.query(keywords=keywords, top_k=top_k)
        if not bm25_hits:
            return []

        chunk_ids = [str(hit["chunk_id"]) for hit in bm25_hits if hit.get("chunk_id")]
        if not chunk_ids:
            return []

        records = self._vector_store.get_by_ids(ids=chunk_ids, trace=trace)
        record_by_id: Dict[str, Dict[str, Any]] = {
            str(item.get("id")): item for item in records if item.get("id")
        }

        merged: List[RetrievalResult] = []
        for hit in bm25_hits:
            chunk_id = str(hit.get("chunk_id", "")).strip()
            if not chunk_id:
                continue
            record = record_by_id.get(chunk_id)
            if not record:
                continue
            merged.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    score=float(hit.get("score", 0.0)),
                    text=str(record.get("text") or ""),
                    metadata=dict(record.get("metadata") or {}),
                )
            )
        return merged
