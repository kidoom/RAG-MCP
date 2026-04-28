"""Core reranker orchestrator with graceful fallback (D6 / F3)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import RetrievalResult
from libs.llm import LLMFactory, LLMSettings as LibLLMSettings
from libs.reranker import (
    BaseReranker,
    RERANK_FALLBACK_KEY,
    RERANK_FALLBACK_REASON_KEY,
    RerankerFactory,
    RerankerSettings,
)


class Reranker:
    """Apply reranking backend and fallback to fusion order when needed."""

    def __init__(self, settings: Settings, backend: Optional[BaseReranker] = None) -> None:
        self._settings = settings
        self._backend = backend or self._build_backend(settings)

    @staticmethod
    def _build_backend(settings: Settings) -> BaseReranker:
        backend_name = (settings.rerank.provider or "none").strip().lower()
        if not settings.rerank.enabled:
            backend_name = "none"

        extra: Dict[str, Any] = {}
        if backend_name == "llm":
            llm = LLMFactory.create_llm(
                LibLLMSettings(
                    provider=settings.llm.provider,
                    model=settings.llm.model,
                    api_key=settings.llm.api_key or None,
                    base_url=settings.llm.base_url or None,
                    azure_endpoint=settings.llm.azure_endpoint or None,
                    deployment_name=settings.llm.deployment_name or None,
                    api_version=settings.llm.api_version or None,
                    temperature=settings.llm.temperature,
                    max_tokens=settings.llm.max_tokens,
                )
            )
            extra["llm"] = llm

        backend_settings = RerankerSettings(
            backend=backend_name,
            model=settings.rerank.model or None,
            top_k=settings.rerank.top_k,
            extra=extra,
        )
        return RerankerFactory.create(backend_settings)

    def rerank(
        self,
        query: str,
        candidates: List[RetrievalResult],
        top_k: Optional[int] = None,
        trace: Optional[TraceContext] = None,
    ) -> List[RetrievalResult]:
        if not candidates:
            return []

        t_start = time.monotonic()
        k = top_k if top_k is not None else self._settings.rerank.top_k
        if k <= 0:
            raise ValueError("top_k must be positive")

        payload = [
            {
                "id": item.chunk_id,
                "score": float(item.score),
                "text": item.text,
                "metadata": dict(item.metadata),
            }
            for item in candidates
        ]
        by_id = {item.chunk_id: item for item in candidates}

        backend_name = (self._settings.rerank.provider or "none").strip().lower()
        fallback_used = False
        fallback_reason = ""

        try:
            ranked_payload = self._backend.rerank(query=query, candidates=payload, trace=trace)
        except Exception as exc:  # noqa: BLE001 - fallback required by D6
            fallback_used = True
            fallback_reason = str(exc)
            ranked_payload = []

        backend_fallback = bool(
            ranked_payload and ranked_payload[0].get(RERANK_FALLBACK_KEY)
        )
        if ranked_payload:
            rsn = str(ranked_payload[0].get(RERANK_FALLBACK_REASON_KEY, "")).strip()
        else:
            rsn = ""

        if fallback_used or backend_fallback:
            result = self._fallback(
                candidates=candidates, top_k=k,
                reason=fallback_reason or rsn,
            )
            if trace is not None:
                trace.record_stage(
                    "rerank",
                    method=backend_name,
                    backend=backend_name,
                    fallback=True,
                    fallback_reason=fallback_reason or rsn,
                    elapsed_ms=(time.monotonic() - t_start) * 1000.0,
                )
            return result

        ranked: List[RetrievalResult] = []
        seen: set[str] = set()
        for item in ranked_payload:
            chunk_id = str(item.get("id", "")).strip()
            if not chunk_id or chunk_id in seen or chunk_id not in by_id:
                continue
            seen.add(chunk_id)
            base = by_id[chunk_id]
            metadata = dict(base.metadata)
            metadata.update(dict(item.get("metadata") or {}))
            ranked.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    score=float(item.get("score", base.score)),
                    text=str(item.get("text", base.text)),
                    metadata=metadata,
                )
            )
            if len(ranked) >= k:
                break

        if len(ranked) < min(k, len(candidates)):
            for base in candidates:
                if base.chunk_id in seen:
                    continue
                ranked.append(base)
                if len(ranked) >= k:
                    break

        if trace is not None:
            trace.record_stage(
                "rerank",
                method=backend_name,
                backend=backend_name,
                fallback=False,
                elapsed_ms=(time.monotonic() - t_start) * 1000.0,
            )

        return ranked

    def _fallback(
        self, candidates: List[RetrievalResult], top_k: int, reason: str = ""
    ) -> List[RetrievalResult]:
        out: List[RetrievalResult] = []
        for index, item in enumerate(candidates[:top_k]):
            metadata = dict(item.metadata)
            if index == 0:
                metadata["fallback"] = True
                if reason:
                    metadata["fallback_reason"] = reason
            out.append(
                RetrievalResult(
                    chunk_id=item.chunk_id,
                    score=item.score,
                    text=item.text,
                    metadata=metadata,
                )
            )
        return out
