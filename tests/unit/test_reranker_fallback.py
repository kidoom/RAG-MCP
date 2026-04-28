"""Unit tests for Core-layer reranker fallback behavior (D6 / F3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

from core.query_engine.reranker import Reranker
from core.trace.trace_context import TraceContext
from core.types import RetrievalResult
from libs.reranker import RERANK_FALLBACK_KEY


class FakeBackendRaises:
    def rerank(self, query: str, candidates: List[Dict[str, Any]], trace: Any = None) -> List[Dict[str, Any]]:
        raise RuntimeError("backend down")


class FakeBackendFallbackFlag:
    def rerank(self, query: str, candidates: List[Dict[str, Any]], trace: Any = None) -> List[Dict[str, Any]]:
        out = [dict(c) for c in candidates]
        out[0][RERANK_FALLBACK_KEY] = True
        out[0]["_rerank_fallback_reason"] = "timeout"
        return out


class FakeBackendSuccess:
    def rerank(self, query: str, candidates: List[Dict[str, Any]], trace: Any = None) -> List[Dict[str, Any]]:
        return [
            {"id": "c3", "score": 9.0},
            {"id": "c1", "score": 8.0},
            {"id": "c2", "score": 7.0},
        ]


@dataclass
class _RerankCfg:
    enabled: bool = True
    provider: str = "none"
    model: str = ""
    top_k: int = 2


@dataclass
class _Settings:
    rerank: Any


def _settings() -> _Settings:
    return _Settings(rerank=_RerankCfg())


def _candidates() -> List[RetrievalResult]:
    return [
        RetrievalResult(chunk_id="c1", score=0.9, text="t1", metadata={}),
        RetrievalResult(chunk_id="c2", score=0.8, text="t2", metadata={}),
        RetrievalResult(chunk_id="c3", score=0.7, text="t3", metadata={}),
    ]


def test_reranker_fallbacks_when_backend_raises() -> None:
    reranker = Reranker(settings=_settings(), backend=FakeBackendRaises())  # type: ignore[arg-type]

    out = reranker.rerank(query="q", candidates=_candidates(), top_k=2)

    assert [item.chunk_id for item in out] == ["c1", "c2"]
    assert out[0].metadata["fallback"] is True
    assert "backend down" in out[0].metadata["fallback_reason"]


def test_reranker_fallbacks_when_backend_signals_fallback() -> None:
    reranker = Reranker(settings=_settings(), backend=FakeBackendFallbackFlag())  # type: ignore[arg-type]

    out = reranker.rerank(query="q", candidates=_candidates(), top_k=2)

    assert [item.chunk_id for item in out] == ["c1", "c2"]
    assert out[0].metadata["fallback"] is True
    assert out[0].metadata["fallback_reason"] == "timeout"


def test_reranker_reorders_when_backend_succeeds() -> None:
    reranker = Reranker(settings=_settings(), backend=FakeBackendSuccess())  # type: ignore[arg-type]

    out = reranker.rerank(query="q", candidates=_candidates(), top_k=2)

    assert [item.chunk_id for item in out] == ["c3", "c1"]
    assert out[0].metadata.get("fallback") is None


def test_reranker_validates_top_k() -> None:
    reranker = Reranker(settings=_settings(), backend=FakeBackendSuccess())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="top_k must be positive"):
        reranker.rerank(query="q", candidates=_candidates(), top_k=0)


def test_reranker_records_trace_on_success() -> None:
    """F3: assert trace contains rerank stage on success."""
    reranker = Reranker(settings=_settings(), backend=FakeBackendSuccess())  # type: ignore[arg-type]
    trace = TraceContext(trace_type="query")

    out = reranker.rerank(query="q", candidates=_candidates(), top_k=2, trace=trace)

    assert len(out) == 2
    stage_names = [s["stage"] for s in trace.stages]
    assert "rerank" in stage_names
    rerank_entry = trace.stages[0]
    assert rerank_entry["fallback"] is False
    assert "elapsed_ms" in rerank_entry
    assert rerank_entry["method"] == "none"


def test_reranker_records_trace_on_fallback() -> None:
    """F3: assert trace records fallback info when backend raises."""
    reranker = Reranker(settings=_settings(), backend=FakeBackendRaises())  # type: ignore[arg-type]
    trace = TraceContext(trace_type="query")

    out = reranker.rerank(query="q", candidates=_candidates(), top_k=2, trace=trace)

    assert len(out) == 2
    rerank_entry = trace.stages[0]
    assert rerank_entry["stage"] == "rerank"
    assert rerank_entry["fallback"] is True
    assert "backend down" in rerank_entry["fallback_reason"]
    assert "elapsed_ms" in rerank_entry

