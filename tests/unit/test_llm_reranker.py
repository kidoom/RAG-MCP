import pytest

from src.libs.llm.base_llm import BaseLLM, LLMSettings
from src.libs.reranker import (
    LLMReranker,
    RERANK_FALLBACK_KEY,
    RERANK_FALLBACK_REASON_KEY,
    RerankerFactory,
    RerankerSettings,
)


class MockLLM(BaseLLM):
    def __init__(self, text: str = "", exc: Exception | None = None):
        super().__init__(LLMSettings(provider="mock", model="mock"))
        self._text = text
        self._exc = exc

    def generate(self, prompt: str, **kwargs) -> str:
        if self._exc is not None:
            raise self._exc
        return self._text

    def chat(self, messages, **kwargs) -> str:
        raise NotImplementedError


_MINIMAL_TEMPLATE = "You rank documents.\n\nQuery:"


def test_llm_reranker_orders_by_ranked_ids():
    llm = MockLLM(
        '{"ranked_ids": ["b", "a", "c"]}',
    )
    settings = RerankerSettings(
        backend="llm",
        extra={
            "llm": llm,
            "rerank_prompt_template": _MINIMAL_TEMPLATE,
        },
    )
    reranker = LLMReranker(settings, llm)
    candidates = [
        {"id": "a", "text": "first"},
        {"id": "b", "text": "second"},
        {"id": "c", "text": "third"},
    ]

    out = reranker.rerank("q", candidates)

    assert [x["id"] for x in out] == ["b", "a", "c"]


def test_llm_reranker_respects_top_k():
    llm = MockLLM('{"ranked_ids": ["b", "a", "c"]}')
    settings = RerankerSettings(
        backend="llm",
        top_k=2,
        extra={"llm": llm, "rerank_prompt_template": _MINIMAL_TEMPLATE},
    )
    reranker = LLMReranker(settings, llm)
    candidates = [
        {"id": "a", "text": "first"},
        {"id": "b", "text": "second"},
        {"id": "c", "text": "third"},
    ]

    out = reranker.rerank("q", candidates)

    assert [x["id"] for x in out] == ["b", "a"]


def test_llm_reranker_parses_json_fence():
    llm = MockLLM('```json\n{"ranked_ids": ["x", "y"]}\n```')
    settings = RerankerSettings(
        backend="llm",
        extra={"llm": llm, "rerank_prompt_template": _MINIMAL_TEMPLATE},
    )
    reranker = LLMReranker(settings, llm)
    candidates = [{"id": "y", "text": "b"}, {"id": "x", "text": "a"}]

    out = reranker.rerank("q", candidates)

    assert [x["id"] for x in out] == ["x", "y"]


@pytest.mark.parametrize(
    "bad_response,match",
    [
        ("not json", "not valid JSON"),
        ('{"foo": []}', "ranked_ids"),
        ('{"ranked_ids": ["a"]}', "permutation"),
        ('{"ranked_ids": ["a", "a"]}', "duplicate"),
        ('{"ranked_ids": [1, 2]}', "list of strings"),
    ],
)
def test_llm_reranker_invalid_schema_raises(bad_response: str, match: str):
    llm = MockLLM(bad_response)
    settings = RerankerSettings(
        backend="llm",
        extra={"llm": llm, "rerank_prompt_template": _MINIMAL_TEMPLATE},
    )
    reranker = LLMReranker(settings, llm)
    candidates = [{"id": "a", "text": "x"}, {"id": "b", "text": "y"}]

    with pytest.raises(ValueError, match=match):
        reranker.rerank("q", candidates)


def test_llm_reranker_llm_failure_returns_fallback_signal():
    llm = MockLLM(exc=RuntimeError("timeout"))
    settings = RerankerSettings(
        backend="llm",
        top_k=2,
        extra={"llm": llm, "rerank_prompt_template": _MINIMAL_TEMPLATE},
    )
    reranker = LLMReranker(settings, llm)
    candidates = [
        {"id": "a", "text": "1"},
        {"id": "b", "text": "2"},
        {"id": "c", "text": "3"},
    ]

    out = reranker.rerank("q", candidates)

    assert [x["id"] for x in out] == ["a", "b"]
    assert out[0][RERANK_FALLBACK_KEY] is True
    assert "timeout" in out[0][RERANK_FALLBACK_REASON_KEY]


def test_reranker_factory_creates_llm_backend():
    llm = MockLLM('{"ranked_ids": ["z"]}')
    settings = RerankerSettings(
        backend="llm",
        extra={
            "llm": llm,
            "rerank_prompt_template": _MINIMAL_TEMPLATE,
        },
    )

    reranker = RerankerFactory.create(settings)

    assert isinstance(reranker, LLMReranker)


def test_reranker_factory_llm_without_llm_raises():
    settings = RerankerSettings(backend="llm", extra={})

    with pytest.raises(ValueError, match="extra\\['llm'\\]"):
        RerankerFactory.create(settings)


def test_missing_candidate_id_raises():
    llm = MockLLM('{"ranked_ids": ["x"]}')
    settings = RerankerSettings(
        backend="llm",
        extra={"llm": llm, "rerank_prompt_template": _MINIMAL_TEMPLATE},
    )
    reranker = LLMReranker(settings, llm)

    with pytest.raises(ValueError, match="missing required 'id'"):
        reranker.rerank("q", [{"text": "only text"}])
