"""Lightweight custom evaluator metrics implementation."""

from __future__ import annotations

from typing import Dict, Set

from .base_evaluator import BaseEvaluator, EvaluationInput


# CustomEvaluator 类实现了轻量级的检索评估指标计算，包括命中率和平均倒数排名（MRR）。它继承自 BaseEvaluator 基类，并实现了 evaluate 方法。
class CustomEvaluator(BaseEvaluator):
    """Compute lightweight retrieval metrics such as hit rate and MRR."""

    def evaluate(self, payload: EvaluationInput, trace=None) -> Dict[str, float]:
        if not payload.golden_ids:
            raise ValueError("golden_ids cannot be empty")

        retrieved = payload.retrieved_ids[: self.settings.top_k]
        golden_set: Set[str] = set(payload.golden_ids)

        hit_rate = 1.0 if any(doc_id in golden_set for doc_id in retrieved) else 0.0
        mrr = self._compute_mrr(retrieved, golden_set)

        return {
            "hit_rate": hit_rate,
            "mrr": mrr,
        }

    @staticmethod
    def _compute_mrr(retrieved_ids: list[str], golden_ids: Set[str]) -> float:
        for index, doc_id in enumerate(retrieved_ids, start=1):
            if doc_id in golden_ids:
                return 1.0 / index
        return 0.0
