"""Unit tests for Fusion RRF implementation (D4)."""

from __future__ import annotations

import pytest

from core.query_engine import Fusion
from core.types import RetrievalResult


def _r(chunk_id: str, score: float, text: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id,
        score=score,
        text=text,
        metadata={"source": f"{chunk_id}.md"},
    )


def test_fusion_rrf_produces_deterministic_order() -> None:
    dense = [_r("a", 0.9, "dense-a"), _r("b", 0.8, "dense-b"), _r("c", 0.7, "dense-c")]
    sparse = [_r("b", 2.0, "sparse-b"), _r("a", 1.8, "sparse-a"), _r("d", 1.0, "sparse-d")]
    fusion = Fusion(rrf_k=60)

    out1 = fusion.fuse(dense_results=dense, sparse_results=sparse, top_k=4)
    out2 = fusion.fuse(dense_results=dense, sparse_results=sparse, top_k=4)

    assert [item.chunk_id for item in out1] == [item.chunk_id for item in out2]
    assert [item.chunk_id for item in out1] == ["a", "b", "c", "d"]
    assert out1[0].score == pytest.approx(out1[1].score)
    assert out1[1].score > out1[2].score
    assert out1[2].score == pytest.approx(out1[3].score)


def test_fusion_rrf_k_is_configurable_and_affects_scores() -> None:
    dense = [_r("x", 0.9, "x"), _r("y", 0.8, "y")]
    sparse = [_r("x", 1.1, "x"), _r("z", 1.0, "z")]
    fusion_k_10 = Fusion(rrf_k=10)
    fusion_k_100 = Fusion(rrf_k=100)

    out_10 = fusion_k_10.fuse(dense_results=dense, sparse_results=sparse, top_k=3)
    out_100 = fusion_k_100.fuse(dense_results=dense, sparse_results=sparse, top_k=3)
    score_x_10 = next(item.score for item in out_10 if item.chunk_id == "x")
    score_x_100 = next(item.score for item in out_100 if item.chunk_id == "x")

    assert score_x_10 != score_x_100
    assert score_x_10 > score_x_100


def test_fusion_rrf_handles_single_route_and_input_validation() -> None:
    fusion = Fusion(rrf_k=60)
    dense_only = [_r("a", 0.9, "dense-a"), _r("b", 0.8, "dense-b")]

    out = fusion.fuse(dense_results=dense_only, sparse_results=[], top_k=1)
    assert [item.chunk_id for item in out] == ["a"]
    assert out[0].text == "dense-a"

    with pytest.raises(ValueError, match="top_k must be positive"):
        fusion.fuse(dense_results=dense_only, sparse_results=[], top_k=0)
    with pytest.raises(ValueError, match="rrf_k must be positive"):
        Fusion(rrf_k=0)
