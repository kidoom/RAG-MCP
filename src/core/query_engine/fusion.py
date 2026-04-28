"""Result fusion module using Reciprocal Rank Fusion (RRF) (D4)."""

from __future__ import annotations

from typing import Dict, List, Optional

from core.settings import Settings
from core.types import RetrievalResult


class Fusion:
    # 融合dense和sparse排名，返回一个确定性的排名   
    """Fuse dense and sparse rankings into a single deterministic ranking."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        rrf_k: Optional[int] = None,
    ) -> None:
        if rrf_k is not None:
            if rrf_k <= 0:
                raise ValueError("rrf_k must be positive")
            self._rrf_k = int(rrf_k)
        elif settings is not None:
            self._rrf_k = int(settings.retrieval.rrf_k)
        else:
            self._rrf_k = 60

    @property
    def rrf_k(self) -> int:
        return self._rrf_k

    def fuse(
        self,
        dense_results: List[RetrievalResult],
        sparse_results: List[RetrievalResult],
        top_k: int,
    ) -> List[RetrievalResult]:
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        if not dense_results and not sparse_results:
            return []

        aggregate_scores: Dict[str, float] = {}
        payload_by_id: Dict[str, RetrievalResult] = {}

        self._merge_rankings(dense_results, aggregate_scores, payload_by_id)
        self._merge_rankings(sparse_results, aggregate_scores, payload_by_id)

        ranked_ids = sorted(
            aggregate_scores.keys(),
            key=lambda chunk_id: (-aggregate_scores[chunk_id], chunk_id),
        )

        fused: List[RetrievalResult] = []
        for chunk_id in ranked_ids[:top_k]:
            base = payload_by_id[chunk_id]
            fused.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    score=float(aggregate_scores[chunk_id]),
                    text=base.text,
                    metadata=dict(base.metadata),
                )
            )
        return fused

    def _merge_rankings(
        self,
        ranking: List[RetrievalResult],
        aggregate_scores: Dict[str, float],
        payload_by_id: Dict[str, RetrievalResult],
    ) -> None:
        for rank, item in enumerate(ranking, start=1):
            chunk_id = str(item.chunk_id).strip()
            if not chunk_id:
                continue
            if chunk_id not in payload_by_id:
                payload_by_id[chunk_id] = item
            aggregate_scores[chunk_id] = aggregate_scores.get(chunk_id, 0.0) + (
                1.0 / (self._rrf_k + rank)
            )
