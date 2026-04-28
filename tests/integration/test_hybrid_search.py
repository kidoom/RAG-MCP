"""Integration-style tests for HybridSearch orchestration (D5 / F3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from core.query_engine import Fusion, HybridSearch, QueryProcessor
from core.trace.trace_context import TraceContext
from core.types import RetrievalResult


@dataclass
class _MinimalSettings:
    retrieval: Any
    embedding: Any
    rerank: Any


def _make_settings() -> _MinimalSettings:
    retrieval = type("RetrievalCfg", (), {"rrf_k": 60})()
    embedding = type("EmbeddingCfg", (), {"provider": "openai"})()
    rerank = type("RerankCfg", (), {"provider": "none", "enabled": False})()
    return _MinimalSettings(retrieval=retrieval, embedding=embedding, rerank=rerank)


class FakeDenseRetriever:
    def __init__(
        self, results: Optional[List[RetrievalResult]] = None, error: Optional[Exception] = None
    ):
        self._results = results or []
        self._error = error
        self.calls: List[Dict[str, Any]] = []

    def retrieve(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        trace: Any = None,
    ) -> List[RetrievalResult]:
        self.calls.append(
            {"query": query, "top_k": top_k, "filters": filters or {}, "trace": trace}
        )
        if self._error is not None:
            raise self._error
        return self._results


class FakeSparseRetriever:
    def __init__(
        self, results: Optional[List[RetrievalResult]] = None, error: Optional[Exception] = None
    ):
        self._results = results or []
        self._error = error
        self.calls: List[Dict[str, Any]] = []

    def retrieve(self, keywords: List[str], top_k: int, trace: Any = None) -> List[RetrievalResult]:
        self.calls.append({"keywords": keywords, "top_k": top_k, "trace": trace})
        if self._error is not None:
            raise self._error
        return self._results


def _r(chunk_id: str, score: float, collection: str, doc_type: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=f"text-{chunk_id}",
        metadata={"collection": collection, "doc_type": doc_type},
    )


def test_hybrid_search_returns_top_k_with_metadata_filters() -> None:
    dense = FakeDenseRetriever(
        results=[
            _r("a", 0.9, "docs", "guide"),
            _r("b", 0.8, "notes", "faq"),
            _r("c", 0.7, "docs", "faq"),
        ]
    )
    sparse = FakeSparseRetriever(
        results=[
            _r("b", 3.0, "notes", "faq"),
            _r("c", 2.0, "docs", "faq"),
            _r("d", 1.0, "docs", "guide"),
        ]
    )
    searcher = HybridSearch(
        settings=_make_settings(),
        query_processor=QueryProcessor(),
        dense_retriever=dense,
        sparse_retriever=sparse,
        fusion=Fusion(rrf_k=60),
    )

    results = searcher.search(
        query="How to configure Azure OpenAI for RAG?",
        top_k=2,
        filters={"collection": "docs"},
    )

    assert [item.chunk_id for item in results] == ["c", "a"]
    assert all(item.metadata["collection"] == "docs" for item in results)
    assert dense.calls[0]["filters"] == {"collection": "docs"}
    assert sparse.calls[0]["keywords"]


def test_hybrid_search_falls_back_to_sparse_when_dense_fails() -> None:
    dense = FakeDenseRetriever(error=RuntimeError("dense down"))
    sparse = FakeSparseRetriever(results=[_r("s1", 2.0, "docs", "guide")])
    searcher = HybridSearch(
        settings=_make_settings(),
        query_processor=QueryProcessor(),
        dense_retriever=dense,
        sparse_retriever=sparse,
        fusion=Fusion(rrf_k=60),
    )

    results = searcher.search(query="azure rag", top_k=3, filters={"collection": "docs"})

    assert [item.chunk_id for item in results] == ["s1"]


def test_hybrid_search_raises_when_both_routes_fail() -> None:
    searcher = HybridSearch(
        settings=_make_settings(),
        query_processor=QueryProcessor(),
        dense_retriever=FakeDenseRetriever(error=RuntimeError("dense down")),
        sparse_retriever=FakeSparseRetriever(error=RuntimeError("sparse down")),
        fusion=Fusion(rrf_k=60),
    )

    with pytest.raises(RuntimeError, match="both dense and sparse retrieval failed"):
        searcher.search(query="azure rag", top_k=2)


def test_hybrid_search_records_trace_stages() -> None:
    """F3: assert that trace contains all expected query stages."""
    dense = FakeDenseRetriever(
        results=[_r("a", 0.9, "docs", "guide"), _r("b", 0.8, "docs", "faq")]
    )
    sparse = FakeSparseRetriever(
        results=[_r("b", 3.0, "docs", "faq"), _r("c", 2.0, "docs", "guide")]
    )
    searcher = HybridSearch(
        settings=_make_settings(),
        query_processor=QueryProcessor(),
        dense_retriever=dense,
        sparse_retriever=sparse,
        fusion=Fusion(rrf_k=60),
    )

    trace = TraceContext(trace_type="query")
    results = searcher.search(query="azure rag", top_k=2, trace=trace)

    assert len(results) > 0
    stage_names = [s["stage"] for s in trace.stages]
    assert "query_processing" in stage_names
    assert "dense_retrieval" in stage_names
    assert "sparse_retrieval" in stage_names
    assert "fusion" in stage_names

    for entry in trace.stages:
        if entry["stage"] == "dense_retrieval":
            assert entry["method"] == "openai"
            assert "elapsed_ms" in entry
        if entry["stage"] == "sparse_retrieval":
            assert entry["method"] == "bm25"
            assert "elapsed_ms" in entry
        if entry["stage"] == "fusion":
            assert entry["method"] == "rrf"

    trace.finish()
    d = trace.to_dict()
    assert d["trace_type"] == "query"
    assert d["total_elapsed_ms"] >= 0.0


def test_hybrid_search_trace_without_fusion_when_one_route_fails() -> None:
    """F3: when only one route succeeds, fusion stage must not be recorded."""
    dense = FakeDenseRetriever(error=RuntimeError("dense down"))
    sparse = FakeSparseRetriever(results=[_r("s1", 2.0, "docs", "guide")])
    searcher = HybridSearch(
        settings=_make_settings(),
        query_processor=QueryProcessor(),
        dense_retriever=dense,
        sparse_retriever=sparse,
        fusion=Fusion(rrf_k=60),
    )

    trace = TraceContext(trace_type="query")
    results = searcher.search(query="azure rag", top_k=3, trace=trace)

    assert len(results) == 1
    stage_names = [s["stage"] for s in trace.stages]
    assert "fusion" not in stage_names
    assert "dense_retrieval" in stage_names
    assert trace.stages[1]["error"] is True  # dense route errored
