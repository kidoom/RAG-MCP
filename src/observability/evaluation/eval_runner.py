"""EvalRunner — reads golden test set, runs retrieval, and computes metrics (H3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.settings import Settings, load_settings
from libs.evaluator.base_evaluator import BaseEvaluator, EvaluationInput


@dataclass
class EvalReport:
    """Structured evaluation report."""

    test_set_path: str
    total_queries: int
    metrics: Dict[str, float] = field(default_factory=dict)
    per_query: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def hit_rate(self) -> float:
        return self.metrics.get("hit_rate", 0.0)

    @property
    def mrr(self) -> float:
        return self.metrics.get("mrr", 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_set_path": self.test_set_path,
            "total_queries": self.total_queries,
            "metrics": dict(self.metrics),
            "per_query": list(self.per_query),
        }

    def summary(self) -> str:
        lines = [
            f"Eval Report — {self.test_set_path}",
            f"  Queries: {self.total_queries}",
        ]
        for k, v in sorted(self.metrics.items()):
            lines.append(f"  {k}: {v:.4f}")
        return "\n".join(lines)


class EvalRunner:
    """Run golden-test-set based evaluation against the retrieval pipeline.

    Does NOT require a running server — it constructs HybridSearch locally
    and evaluates retrieval quality directly.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        evaluator: Optional[BaseEvaluator] = None,
    ) -> None:
        self._settings = settings or load_settings()
        self._evaluator = evaluator

    @property
    def evaluator(self) -> BaseEvaluator:
        if self._evaluator is None:
            from libs.evaluator.custom_evaluator import CustomEvaluator
            from libs.evaluator.base_evaluator import EvaluatorSettings

            self._evaluator = CustomEvaluator(
                EvaluatorSettings(provider="custom", top_k=self._settings.retrieval.fusion_top_k)
            )
        return self._evaluator

    def run(self, test_set_path: str) -> EvalReport:
        """Load golden test set, run all queries, return EvalReport."""
        path = Path(test_set_path)
        if not path.exists():
            raise FileNotFoundError(f"Golden test set not found: {path}")

        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)

        test_cases = data.get("test_cases", [])
        if not test_cases:
            raise ValueError("test_set must contain a non-empty 'test_cases' list")

        report = EvalReport(
            test_set_path=str(path.resolve()),
            total_queries=len(test_cases),
        )

        aggregate: Dict[str, List[float]] = {}

        for test_case in test_cases:
            query = str(test_case.get("query", ""))
            expected_ids = [str(eid) for eid in test_case.get("expected_chunk_ids", [])]
            expected_sources = [str(es) for es in test_case.get("expected_sources", [])]

            if not query or not expected_ids:
                report.per_query.append({
                    "query": query,
                    "error": "Missing query or expected_chunk_ids",
                })
                continue

            # Run retrieval
            retrieved = self._retrieve(query)

            # Build evaluation input
            payload = EvaluationInput(
                query=query,
                retrieved_ids=retrieved,
                golden_ids=expected_ids,
            )

            eval_result = self.evaluator.evaluate(payload)

            for k, v in eval_result.items():
                aggregate.setdefault(k, []).append(v)

            report.per_query.append({
                "query": query,
                "retrieved_ids": retrieved[:10],
                "expected_ids": expected_ids,
                "metrics": dict(eval_result),
            })

        # Compute aggregate metrics
        for k, values in aggregate.items():
            report.metrics[k] = sum(values) / max(len(values), 1)

        return report

    def _retrieve(self, query: str) -> List[str]:
        """Run hybrid search and return chunk IDs."""
        try:
            from core.query_engine.dense_retriever import DenseRetriever
            from core.query_engine.fusion import Fusion
            from core.query_engine.hybrid_search import HybridSearch
            from core.query_engine.query_processor import QueryProcessor
            from core.query_engine.sparse_retriever import SparseRetriever

            qp = QueryProcessor(self._settings)
            dense = DenseRetriever(self._settings)
            sparse = SparseRetriever()
            fusion = Fusion(rrf_k=self._settings.retrieval.rrf_k)

            hs = HybridSearch(self._settings, qp, dense, sparse, fusion)
            results = hs.search(query, top_k=self._settings.retrieval.fusion_top_k)
            return [r.chunk_id for r in results]
        except Exception:
            # If full pipeline unavailable, return empty (evaluator handles this)
            return []
