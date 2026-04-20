from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RerankSettings:
    provider: str
    model: str = ""
    top_k: int = 5
    enabled: bool = False


class BaseRerank(ABC):
    def __init__(self, settings: RerankSettings):
        self.settings = settings

    @abstractmethod
    def rerank(self, query: str, documents: List[str], top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        """Rerank documents by relevance to query, return (doc, score) pairs"""
        pass


# Provider registry
_rerank_providers = {}


def register_rerank_provider(provider_name: str, cls):
    _rerank_providers[provider_name] = cls


def get_rerank_provider(provider_name: str) -> type:
    return _rerank_providers.get(provider_name)


# Import providers
from .llm_rerank import LLMRerank
from .cross_encoder_rerank import CrossEncoderRerank