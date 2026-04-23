"""Base abstractions for reranker implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RerankerSettings:
    """Configuration for reranker providers."""

    backend: str
    model: Optional[str] = None
    top_k: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout_seconds: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseReranker(ABC):
    """Abstract base class for all reranker providers."""

    def __init__(self, settings: RerankerSettings):
        self.settings = settings

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Return reranked candidates in descending relevance order."""
        raise NotImplementedError


class NoneReranker(BaseReranker):
    """Fallback reranker that preserves the original candidate order."""

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        # Keep behavior explicit and deterministic for fallback flows.
        return list(candidates)
