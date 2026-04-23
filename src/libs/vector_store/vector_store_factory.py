"""Factory for creating vector store instances."""

from __future__ import annotations

from typing import Dict, Type

from .base_vector_store import BaseVectorStore, VectorStoreSettings
from .chroma_store import ChromaStore


class VectorStoreFactory:
    """Factory class for vector store providers."""

    _providers: Dict[str, Type[BaseVectorStore]] = {
        "chroma": ChromaStore,
    }

    @classmethod
    def create(cls, settings: VectorStoreSettings) -> BaseVectorStore:
        """Create a vector store instance based on configured provider."""
        provider_name = settings.provider.lower()
        provider_cls = cls._providers.get(provider_name)

        if not provider_cls:
            available = ", ".join(sorted(cls._providers.keys())) or "none"
            raise ValueError(
                f"Unsupported vector store provider: {provider_name}. "
                f"Available providers: {available}"
            )

        return provider_cls(settings)

    @classmethod
    def register_provider(cls, name: str, provider_cls: Type[BaseVectorStore]) -> None:
        """Register a provider implementation."""
        cls._providers[name.lower()] = provider_cls

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all available vector store providers."""
        return sorted(cls._providers.keys())
