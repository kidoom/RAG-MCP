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
    """Abstract base class for embedding providers."""

    def __init__(self, settings: EmbeddingSettings):
        self.settings = settings

    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    def embed_query(self, query: str) -> List[float]:
        """Embed a single query.
        
        Args:
            query: Query string to embed
            
        Returns:
            Single embedding vector
        """
        pass


# Import providers and factory
from .openai_embedding import OpenAIEmbedding
from .azure_embedding import AzureEmbedding
from .ollama_embedding import OllamaEmbedding
from .qwen_embedding import QwenEmbedding
from .gemini_embedding import GeminiEmbedding
from .embedding_factory import EmbeddingFactory

__all__ = [
    "BaseEmbedding",
    "EmbeddingSettings",
    "EmbeddingFactory",
    "OpenAIEmbedding",
    "AzureEmbedding",
    "OllamaEmbedding",
    "QwenEmbedding",
    "GeminiEmbedding",
]