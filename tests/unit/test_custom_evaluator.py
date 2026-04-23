import pytest

from src.libs.evaluator import (
    BaseEvaluator,
    CustomEvaluator,
    EvaluationInput,
    EvaluatorFactory,
    EvaluatorSettings,
)


class FakeEvaluator(BaseEvaluator):
    def evaluate(self, payload: EvaluationInput, trace=None) -> dict[str, float]:
        return {"fake_score": 1.0}


class TestCustomEvaluator:
    def test_compute_hit_rate_and_mrr_when_hit_on_first_position(self):
        evaluator = CustomEvaluator(EvaluatorSettings(provider="custom", top_k=5))
        payload = EvaluationInput(
            query="what is rag",
            retrieved_ids=["doc_1", "doc_2", "doc_3"],
            golden_ids=["doc_1", "doc_4"],
        )

        metrics = evaluator.evaluate(payload)

        assert metrics["hit_rate"] == 1.0
        assert metrics["mrr"] == 1.0

    def test_compute_metrics_when_hit_on_later_position(self):
        evaluator = CustomEvaluator(EvaluatorSettings(provider="custom", top_k=5))
        payload = EvaluationInput(
            query="what is rerank",
            retrieved_ids=["doc_x", "doc_y", "doc_hit", "doc_z"],
            golden_ids=["doc_hit"],
        )

        metrics = evaluator.evaluate(payload)

        assert metrics["hit_rate"] == 1.0
        assert metrics["mrr"] == pytest.approx(1.0 / 3.0)

    def test_compute_metrics_when_no_hit(self):
        evaluator = CustomEvaluator(EvaluatorSettings(provider="custom", top_k=3))
        payload = EvaluationInput(
            query="no match",
            retrieved_ids=["a", "b", "c", "hit_outside_top_k"],
            golden_ids=["hit_outside_top_k"],
        )

        metrics = evaluator.evaluate(payload)

        assert metrics["hit_rate"] == 0.0
        assert metrics["mrr"] == 0.0

    def test_empty_golden_ids_raises_error(self):
        evaluator = CustomEvaluator(EvaluatorSettings(provider="custom"))
        payload = EvaluationInput(
            query="invalid",
            retrieved_ids=["doc_1"],
            golden_ids=[],
        )

        with pytest.raises(ValueError, match="golden_ids cannot be empty"):
            evaluator.evaluate(payload)


class TestEvaluatorFactory:
    def test_create_custom_evaluator(self):
        evaluator = EvaluatorFactory.create(EvaluatorSettings(provider="custom"))
        assert isinstance(evaluator, CustomEvaluator)

    def test_provider_case_insensitive(self):
        evaluator = EvaluatorFactory.create(EvaluatorSettings(provider="CUSTOM"))
        assert isinstance(evaluator, CustomEvaluator)

    def test_invalid_provider_raises_error(self):
        with pytest.raises(ValueError, match="Unsupported evaluator provider"):
            EvaluatorFactory.create(EvaluatorSettings(provider="unknown"))

    def test_register_provider(self):
        EvaluatorFactory.register_provider("fake", FakeEvaluator)
        evaluator = EvaluatorFactory.create(EvaluatorSettings(provider="fake"))
        assert isinstance(evaluator, FakeEvaluator)

    def test_list_providers(self):
        providers = EvaluatorFactory.list_providers()
        assert "custom" in providers
        assert providers == sorted(providers)
