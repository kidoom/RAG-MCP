import time

import pytest

from src.libs.reranker import (
    CrossEncoderReranker,
    RERANK_FALLBACK_KEY,
    RERANK_FALLBACK_REASON_KEY,
    RerankerFactory,
    RerankerSettings,
)


class MockCrossEncoder:
    """Deterministic scorer: higher score for longer passage text."""

    def predict(self, pairs: list[list[str]]) -> list[float]:
        return [float(len(p[1])) for p in pairs]


class FailingScorer:
    def predict(self, pairs: list[list[str]]) -> list[float]:
        raise RuntimeError("scorer down")


class SlowScorer:
    def predict(self, pairs: list[list[str]]) -> list[float]:
        time.sleep(2.0)
        return [1.0] * len(pairs)


def test_cross_encoder_reranker_sorts_by_scores():
    settings = RerankerSettings(
        backend="cross_encoder",
        extra={"cross_encoder_scorer": MockCrossEncoder()},
    )
    r = CrossEncoderReranker(settings)
    candidates = [
        {"id": "a", "text": "hi"},
        {"id": "b", "text": "hello world"},
        {"id": "c", "text": "x"},
    ]

    out = r.rerank("q", candidates)

    assert [x["id"] for x in out] == ["b", "a", "c"]


def test_cross_encoder_reranker_respects_top_k():
    settings = RerankerSettings(
        backend="cross_encoder",
        top_k=2,
        extra={"cross_encoder_scorer": MockCrossEncoder()},
    )
    r = CrossEncoderReranker(settings)
    candidates = [
        {"id": "a", "text": "aa"},
        {"id": "b", "text": "bbbb"},
        {"id": "c", "text": "c"},
    ]

    out = r.rerank("q", candidates)

    assert [x["id"] for x in out] == ["b", "a"]


def test_cross_encoder_reranker_scorer_failure_sets_fallback():
    settings = RerankerSettings(
        backend="cross_encoder",
        top_k=2,
        extra={"cross_encoder_scorer": FailingScorer()},
    )
    r = CrossEncoderReranker(settings)
    candidates = [
        {"id": "x", "text": "1"},
        {"id": "y", "text": "2"},
        {"id": "z", "text": "3"},
    ]

    out = r.rerank("q", candidates)

    assert [x["id"] for x in out] == ["x", "y"]
    assert out[0][RERANK_FALLBACK_KEY] is True
    assert "scorer down" in out[0][RERANK_FALLBACK_REASON_KEY]


def test_cross_encoder_reranker_predict_timeout_fallback():
    settings = RerankerSettings(
        backend="cross_encoder",
        top_k=2,
        timeout_seconds=0.2,
        extra={"cross_encoder_scorer": SlowScorer()},
    )
    r = CrossEncoderReranker(settings)
    candidates = [
        {"id": "p", "text": "a"},
        {"id": "q", "text": "b"},
        {"id": "r", "text": "c"},
    ]

    out = r.rerank("q", candidates)

    assert [x["id"] for x in out] == ["p", "q"]
    assert out[0][RERANK_FALLBACK_KEY] is True
    assert "exceeded" in out[0][RERANK_FALLBACK_REASON_KEY]


def test_cross_encoder_reranker_wrong_score_count_fallback():
    class BadScorer:
        def predict(self, pairs: list[list[str]]) -> list[float]:
            return [1.0]

    settings = RerankerSettings(
        backend="cross_encoder",
        top_k=2,
        extra={"cross_encoder_scorer": BadScorer()},
    )
    r = CrossEncoderReranker(settings)
    candidates = [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}]

    out = r.rerank("q", candidates)

    assert len(out) == 2
    assert out[0][RERANK_FALLBACK_KEY] is True


def test_reranker_factory_cross_encoder():
    settings = RerankerSettings(
        backend="cross_encoder",
        extra={"cross_encoder_scorer": MockCrossEncoder()},
    )
    r = RerankerFactory.create(settings)
    assert isinstance(r, CrossEncoderReranker)


def test_missing_candidate_id_raises():
    settings = RerankerSettings(
        backend="cross_encoder",
        extra={"cross_encoder_scorer": MockCrossEncoder()},
    )
    r = CrossEncoderReranker(settings)

    with pytest.raises(ValueError, match="missing required 'id'"):
        r.rerank("q", [{"text": "only"}])
