"""Cross-encoder reranker: scores query–passage pairs and sorts candidates."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, List, Optional

from .base_reranker import (
    BaseReranker,
    RERANK_FALLBACK_KEY,
    RERANK_FALLBACK_REASON_KEY,
    RerankerSettings,
)

_DEFAULT_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _coerce_scores(raw: Any, n: int) -> List[float]:
    if hasattr(raw, "tolist"):
        raw = raw.tolist()
    if not isinstance(raw, (list, tuple)):
        raise TypeError(f"scorer must return a sequence of scores, got {type(raw).__name__}")
    out = [float(x) for x in raw]
    if len(out) != n:
        raise ValueError(
            f"cross-encoder returned {len(out)} scores for {n} candidates"
        )
    return out


class CrossEncoderReranker(BaseReranker):
    """
    Rerank using a cross-encoder model (sentence-transformers) or an injected scorer.

    Tests should pass ``settings.extra['cross_encoder_scorer']`` with a ``predict(pairs)``
    method, where ``pairs`` is ``List[List[str]]`` of ``[query, passage]``.
    """

    def __init__(self, settings: RerankerSettings):
        super().__init__(settings)
        self._scorer = self._resolve_scorer(settings)

    def _resolve_scorer(self, settings: RerankerSettings) -> Any:
        injected = settings.extra.get("cross_encoder_scorer")
        if injected is not None:
            return injected
        model = settings.model or _DEFAULT_CROSS_ENCODER_MODEL
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise ImportError(
                "sentence-transformers is required for cross_encoder reranker unless "
                "settings.extra['cross_encoder_scorer'] is provided"
            ) from exc
        return CrossEncoder(model)

    def _resolve_top_k(self, n: int) -> int:
        if self.settings.top_k is not None:
            return min(self.settings.top_k, n)
        return n

    def _predict_scores(self, pairs: List[List[str]]) -> Any:
        timeout = self.settings.timeout_seconds
        if timeout is None or timeout <= 0:
            return self._scorer.predict(pairs)

        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(self._scorer.predict, pairs)
            try:
                return fut.result(timeout=timeout)
            except FuturesTimeoutError as exc:
                raise TimeoutError(
                    f"cross-encoder predict exceeded {timeout} seconds"
                ) from exc

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        for i, c in enumerate(candidates):
            if "id" not in c:
                raise ValueError(f"candidates[{i}] is missing required 'id' key")

        if len(candidates) == 1:
            return [dict(candidates[0])]

        k = self._resolve_top_k(len(candidates))
        texts = [str(c.get("text", "")) for c in candidates]
        pairs: List[List[str]] = [[query, t] for t in texts]

        try:
            raw = self._predict_scores(pairs)
            scores = _coerce_scores(raw, len(candidates))
        except Exception as exc:  # noqa: BLE001 — intentional fallback for D6
            out = [dict(c) for c in candidates[:k]]
            if out:
                out[0][RERANK_FALLBACK_KEY] = True
                out[0][RERANK_FALLBACK_REASON_KEY] = str(exc)
            return out

        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [dict(item[0]) for item in scored[:k]]
