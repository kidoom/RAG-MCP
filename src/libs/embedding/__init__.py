from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class EmbeddingSettings:
    provider: str
    model: str
    dimensions: int
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    azure_endpoint: Optional[str] = None
    deployment_name: Optional[str] = None
    api_version: Optional[str] = None


class BaseEmbedding(ABC):
    def __init__(self, settings: EmbeddingSettings):
        self.settings = settings

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts"""
        pass

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """Embed a single query"""
        pass


# Provider registry
_embedding_providers = {}


def register_embedding_provider(provider_name: str, cls):
    _embedding_providers[provider_name] = cls


def get_embedding_provider(provider_name: str) -> type:
    return _embedding_providers.get(provider_name)


# Import providers
from .openai_embedding import OpenAIEmbedding
from .azure_embedding import AzureEmbedding
from .ollama_embedding import OllamaEmbedding
from .qwen_embedding import QwenEmbedding
from .gemini_embedding import GeminiEmbedding