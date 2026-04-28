"""Hybrid retrieval orchestrator for dense/sparse/fusion pipeline (D5 / F3)."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import RetrievalResult

from .dense_retriever import DenseRetriever
from .fusion import Fusion
from .query_processor import QueryProcessor
from .sparse_retriever import SparseRetriever


class HybridSearch:
    """Orchestrate query processing, parallel retrieval, fusion, and filtering."""

    def __init__(
        self,
        settings: Settings,
        query_processor: QueryProcessor,
        dense_retriever: DenseRetriever,
        sparse_retriever: SparseRetriever,
        fusion: Fusion,
    ) -> None:
        self._settings = settings
        self._query_processor = query_processor
        self._dense_retriever = dense_retriever
        self._sparse_retriever = sparse_retriever
        self._fusion = fusion

    def search(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[TraceContext] = None,
    ) -> List[RetrievalResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        t_start = time.monotonic()

        processed = self._query_processor.process(query=query, filters=filters)
        t_qp = time.monotonic()

        # Recall a wider candidate pool so post-filtering still has enough headroom.
        recall_k = max(top_k * 2, top_k)

        dense_results: List[RetrievalResult] = []
        sparse_results: List[RetrievalResult] = []
        dense_error: Optional[Exception] = None
        sparse_error: Optional[Exception] = None

        with ThreadPoolExecutor(max_workers=2) as executor:
            dense_future = executor.submit(
                self._dense_retriever.retrieve,
                processed.normalized_query,
                recall_k,
                processed.filters,
                trace,
            )
            sparse_future = executor.submit(
                self._sparse_retriever.retrieve,
                processed.keywords,
                recall_k,
                trace,
            )

            try:
                dense_results = dense_future.result()
            except Exception as exc:  # pragma: no cover - fallback behavior tested
                dense_error = exc

            try:
                sparse_results = sparse_future.result()
            except Exception as exc:  # pragma: no cover - fallback behavior tested
                sparse_error = exc

        t_retrieval = time.monotonic()

        if trace is not None:
            trace.record_stage(
                "query_processing",
                method="rule",
                elapsed_ms=(t_qp - t_start) * 1000.0,
                keywords=processed.keywords,
                filters=processed.filters,
            )
            trace.record_stage(
                "dense_retrieval",
                method=self._settings.embedding.provider,
                result_count=len(dense_results),
                error=bool(dense_error),
                elapsed_ms=(t_retrieval - t_qp) * 1000.0,
            )
            trace.record_stage(
                "sparse_retrieval",
                method="bm25",
                result_count=len(sparse_results),
                error=bool(sparse_error),
                elapsed_ms=(t_retrieval - t_qp) * 1000.0,
            )

        if dense_error is not None and sparse_error is not None:
            raise RuntimeError(
                "both dense and sparse retrieval failed"
            ) from dense_error

        if dense_results and sparse_results:
            candidates = self._fusion.fuse(
                dense_results=dense_results,
                sparse_results=sparse_results,
                top_k=recall_k,
            )
            if trace is not None:
                trace.record_stage(
                    "fusion",
                    method="rrf",
                    rrf_k=self._settings.retrieval.rrf_k,
                    candidate_count=len(candidates),
                )
        elif dense_results:
            candidates = dense_results
        else:
            candidates = sparse_results

        filtered = self._apply_metadata_filters(candidates, processed.filters)
        return filtered[:top_k]

    def _apply_metadata_filters(
        self,
        candidates: Iterable[RetrievalResult],
        filters: Optional[Dict[str, Any]],
    ) -> List[RetrievalResult]:
        if not filters:
            return list(candidates)

        filtered: List[RetrievalResult] = []
        for item in candidates:
            metadata = item.metadata or {}
            matched = True
            for key, expected in filters.items():
                actual = metadata.get(key)
                if not self._match_filter(actual=actual, expected=expected):
                    matched = False
                    break
            if matched:
                filtered.append(item)
        return filtered

    @staticmethod
    def _match_filter(actual: Any, expected: Any) -> bool:
        if isinstance(expected, list):
            expected_values = {str(v) for v in expected}
            if isinstance(actual, list):
                return bool(expected_values & {str(v) for v in actual})
            return str(actual) in expected_values
        return actual == expected
