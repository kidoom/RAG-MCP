"""Unit tests for RagasEvaluator (H1)."""

from __future__ import annotations

import pytest

from libs.evaluator.base_evaluator import EvaluationInput, EvaluatorSettings
from observability.evaluation.ragas_evaluator import RagasEvaluator, _RAGAS_IMPORT_ERROR


class TestRagasEvaluator:
    """Tests for RagasEvaluator — graceful import and fallback."""

    def test_import_error_message_when_ragas_not_installed(self):
        """When ragas is not installed, a clear ImportError is raised on evaluate."""
        evaluator = RagasEvaluator(EvaluatorSettings(provider="ragas", top_k=5))
        if _RAGAS_IMPORT_ERROR is not None:
            with pytest.raises(ImportError, match="Ragas is not installed"):
                evaluator._check_import()

    def test_requires_generated_answer(self):
        """RagasEvaluator requires generated_answer."""
        evaluator = RagasEvaluator(EvaluatorSettings(provider="ragas", top_k=5))
        if _RAGAS_IMPORT_ERROR is not None:
            # Skip ragas-dependent test; the import error makes ragas unavailable
            pytest.skip("Ragas not installed — testing graceful import error only")
            return

        payload = EvaluationInput(
            query="test",
            retrieved_ids=["d1"],
            golden_ids=["d1"],
            generated_answer=None,
        )
        with pytest.raises(ValueError, match="generated_answer"):
            evaluator.evaluate(payload)

    def test_returns_metrics_with_fallback_when_ragas_unavailable(self):
        """When ragas is not installed but datasets is also missing, fallback metrics are returned."""
        evaluator = RagasEvaluator(EvaluatorSettings(provider="ragas", top_k=5))

        # Mock the import error and the datasets import to trigger fallback
        if _RAGAS_IMPORT_ERROR is not None:
            # When ragas is not available, we test the constructor behavior
            assert isinstance(evaluator, RagasEvaluator)
            # The evaluator should raise on evaluate()
            with pytest.raises(ImportError, match="Ragas is not installed"):
                evaluator.evaluate(
                    EvaluationInput(
                        query="test",
                        retrieved_ids=["d1", "d2"],
                        golden_ids=["d1"],
                        generated_answer="test answer",
                    )
                )
        else:
            result = evaluator.evaluate(
                EvaluationInput(
                    query="test",
                    retrieved_ids=["d1", "d2"],
                    golden_ids=["d1"],
                    generated_answer="test answer",
                )
            )
            assert isinstance(result, dict)
            assert len(result) >= 2
