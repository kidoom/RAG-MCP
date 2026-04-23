"""Factory for creating reranker instances."""

from __future__ import annotations

from typing import Dict, Type

from .base_reranker import BaseReranker, NoneReranker, RerankerSettings
from .llm_reranker import LLMReranker


class RerankerFactory:
    """Factory class for reranker providers."""

    _providers: Dict[str, Type[BaseReranker]] = {
        "none": NoneReranker,
    }

    @classmethod
    def create(cls, settings: RerankerSettings) -> BaseReranker:
        """Create a reranker instance based on configured backend."""
        backend_name = settings.backend.lower()
        if backend_name == "llm":
            llm = settings.extra.get("llm")
            if llm is None:
                raise ValueError(
                    "Reranker backend 'llm' requires a BaseLLM instance in settings.extra['llm']"
                )
            return LLMReranker(settings, llm)

        provider_cls = cls._providers.get(backend_name)

        if not provider_cls:
            available = ", ".join(sorted(cls._providers.keys())) or "none"
            raise ValueError(
                f"Unsupported reranker backend: {backend_name}. "
                f"Available backends: {available}"
            )

        return provider_cls(settings)

    @classmethod
    def register_provider(cls, name: str, provider_cls: Type[BaseReranker]) -> None:
        """Register a reranker provider implementation."""
        cls._providers[name.lower()] = provider_cls

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all available reranker providers."""
        return sorted(set(cls._providers.keys()) | {"llm"})
