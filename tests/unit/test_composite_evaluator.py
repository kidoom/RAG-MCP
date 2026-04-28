"""Unit tests for CompositeEvaluator (H2)."""

from __future__ import annotations

import pytest

from libs.evaluator.base_evaluator import (
    BaseEvaluator,
    EvaluationInput,
    EvaluatorSettings,
)
from observability.evaluation.composite_evaluator import CompositeEvaluator


class _MockEvaluatorA(BaseEvaluator):
    def evaluate(self, payload, trace=None):
        return {"metric_a": 0.9, "metric_b": 0.8}


class _MockEvaluatorB(BaseEvaluator):
    def evaluate(self, payload, trace=None):
        return {"metric_c": 0.7}


class _SlowEvaluator(BaseEvaluator):
    def evaluate(self, payload, trace=None):
        import time
        time.sleep(0.05)
        return {"slow_metric": 1.0}


class TestCompositeEvaluator:
    """Tests for CompositeEvaluator contract and parallel execution."""

    def test_combines_two_evaluators(self):
        a = _MockEvaluatorA(EvaluatorSettings(provider="mock_a"))
        b = _MockEvaluatorB(EvaluatorSettings(provider="mock_b"))
        composite = CompositeEvaluator([a, b])

        payload = EvaluationInput(
            query="test",
            retrieved_ids=["d1"],
            golden_ids=["d1"],
        )
        metrics = composite.evaluate(payload)

        assert metrics["mock_a_metric_a"] == 0.9
        assert metrics["mock_a_metric_b"] == 0.8
        assert metrics["mock_b_metric_c"] == 0.7

    def test_empty_list_raises_error(self):
        with pytest.raises(ValueError, match="At least one evaluator"):
            CompositeEvaluator([])

    def test_evaluators_property_returns_copy(self):
        a = _MockEvaluatorA(EvaluatorSettings(provider="mock_a"))
        composite = CompositeEvaluator([a])

        evals = composite.evaluators
        evals.pop()
        assert len(composite.evaluators) == 1  # original unchanged

    def test_parallel_execution_runs_all(self):
        a = _SlowEvaluator(EvaluatorSettings(provider="slow_a"))
        b = _SlowEvaluator(EvaluatorSettings(provider="slow_b"))
        composite = CompositeEvaluator([a, b])

        payload = EvaluationInput(
            query="parallel test",
            retrieved_ids=["d1"],
            golden_ids=["d1"],
        )

        metrics = composite.evaluate(payload)
        assert "slow_a_slow_metric" in metrics
        assert "slow_b_slow_metric" in metrics

    def test_evaluator_error_is_captured(self):
        class _ErrorEvaluator(BaseEvaluator):
            def evaluate(self, payload, trace=None):
                raise RuntimeError("simulated failure")

        a = _MockEvaluatorA(EvaluatorSettings(provider="ok"))
        b = _ErrorEvaluator(EvaluatorSettings(provider="fail"))

        composite = CompositeEvaluator([a, b])

        payload = EvaluationInput(
            query="test",
            retrieved_ids=["d1"],
            golden_ids=["d1"],
        )
        metrics = composite.evaluate(payload)

        # The OK evaluator should still produce results
        assert "ok_metric_a" in metrics
        # The failed evaluator should produce an error placeholder
        assert "fail_error" in metrics
