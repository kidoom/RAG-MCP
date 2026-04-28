"""Composite evaluator — parallel execution of multiple evaluators (H2)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from libs.evaluator.base_evaluator import BaseEvaluator, EvaluationInput


class CompositeEvaluator:
    """Combine multiple evaluators and execute them in parallel.

    Usage::

        composite = CompositeEvaluator([ragas_eval, custom_eval])
        metrics = composite.evaluate(payload)
        # metrics == {"ragas_faithfulness": 0.9, "custom_hit_rate": 1.0, ...}
    """

    def __init__(self, evaluators: List[BaseEvaluator]) -> None:
        if not evaluators:
            raise ValueError("At least one evaluator is required for CompositeEvaluator")
        self._evaluators = list(evaluators)

    @property
    def evaluators(self) -> List[BaseEvaluator]:
        return list(self._evaluators)

    def evaluate(
        self,
        payload: EvaluationInput,
        trace: Optional[Any] = None,
    ) -> Dict[str, float]:
        """Run all evaluators in parallel and merge their metric dictionaries.

        Metric keys are prefixed with the evaluator provider name to avoid collisions.
        """
        results: Dict[str, float] = {}

        max_workers = min(len(self._evaluators), 8)

        def _run_one(evaluator: BaseEvaluator) -> Dict[str, float]:
            try:
                raw = evaluator.evaluate(payload, trace=trace)
                provider = evaluator.settings.provider
                return {f"{provider}_{k}": float(v) for k, v in raw.items()}
            except Exception as exc:
                return {f"{evaluator.settings.provider}_error": 0.0}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_run_one, e): e for e in self._evaluators}
            for future in as_completed(futures):
                try:
                    partial = future.result()
                    results.update(partial)
                except Exception:
                    evaluator = futures[future]
                    results[f"{evaluator.settings.provider}_error"] = 0.0

        return results
