from typing import Dict, Type
from . import BaseEmbedding, EmbeddingSettings
from .openai_embedding import OpenAIEmbedding
from .azure_embedding import AzureEmbedding
from .ollama_embedding import OllamaEmbedding
from .qwen_embedding import QwenEmbedding
from .gemini_embedding import GeminiEmbedding


class EmbeddingFactory:
    """Factory class for creating Embedding instances."""

    _providers: Dict[str, Type[BaseEmbedding]] = {
        "openai": OpenAIEmbedding,
        "azure": AzureEmbedding,
        "ollama": OllamaEmbedding,
        "qwen": QwenEmbedding,
        "gemini": GeminiEmbedding,
    }

    @classmethod
    def create(cls, settings: EmbeddingSettings) -> BaseEmbedding:
        """Create an Embedding instance based on the provider in settings."""
        provider_name = settings.provider.lower()
        provider_cls = cls._providers.get(provider_name)

        if not provider_cls:
            raise ValueError(f"Unsupported embedding provider: {provider_name}")

        return provider_cls(settings)

    @classmethod
    def register_provider(cls, name: str, provider_cls: Type[BaseEmbedding]):
        """Register a new embedding provider."""
        cls._providers[name.lower()] = provider_cls

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all available providers."""
        return list(cls._providers.keys())
