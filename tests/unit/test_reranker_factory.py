import pytest

from src.libs.reranker import (
    BaseReranker,
    NoneReranker,
    RerankerFactory,
    RerankerSettings,
)


class FakeReranker(BaseReranker):
    def rerank(self, query: str, candidates: list[dict], trace=None) -> list[dict]:
        return sorted(candidates, key=lambda item: item.get("score", 0.0), reverse=True)


class TestRerankerFactory:
    def test_create_none_reranker(self):
        settings = RerankerSettings(backend="none")
        reranker = RerankerFactory.create(settings)

        assert isinstance(reranker, NoneReranker)
        assert reranker.settings.backend == "none"

    def test_backend_case_insensitive(self):
        settings = RerankerSettings(backend="NONE")
        reranker = RerankerFactory.create(settings)

        assert isinstance(reranker, NoneReranker)

    def test_unknown_backend_raises_error(self):
        settings = RerankerSettings(backend="unknown")

        with pytest.raises(ValueError, match="Unsupported reranker backend"):
            RerankerFactory.create(settings)

    def test_register_provider(self):
        RerankerFactory.register_provider("fake", FakeReranker)
        settings = RerankerSettings(backend="fake")

        reranker = RerankerFactory.create(settings)

        assert isinstance(reranker, FakeReranker)

    def test_list_providers(self):
        providers = RerankerFactory.list_providers()

        assert "none" in providers
        assert providers == sorted(providers)


class TestNoneRerankerBehavior:
    def test_none_reranker_preserves_order(self):
        reranker = NoneReranker(RerankerSettings(backend="none"))
        candidates = [
            {"id": "c3", "score": 0.1},
            {"id": "c1", "score": 0.9},
            {"id": "c2", "score": 0.5},
        ]

        result = reranker.rerank("query", candidates)

        assert [item["id"] for item in result] == ["c3", "c1", "c2"]
        assert result is not candidates

    def test_base_reranker_is_abstract(self):
        settings = RerankerSettings(backend="none")
        with pytest.raises(TypeError):
            BaseReranker(settings)
