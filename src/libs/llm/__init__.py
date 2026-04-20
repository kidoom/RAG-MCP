from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


@dataclass
class LLMSettings:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    azure_endpoint: Optional[str] = None
    deployment_name: Optional[str] = None
    api_version: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 4096


class BaseLLM(ABC):
    def __init__(self, settings: LLMSettings):
        self.settings = settings

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt"""
        pass

    @abstractmethod
    def generate_with_messages(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Generate text from chat messages"""
        pass


# Provider registry
_llm_providers = {}


def register_llm_provider(provider_name: str, cls):
    _llm_providers[provider_name] = cls


def get_llm_provider(provider_name: str) -> type:
    return _llm_providers.get(provider_name)


# Import providers
from .openai_llm import OpenAILLM
from .azure_llm import AzureLLM
from .ollama_llm import OllamaLLM
from .deepseek_llm import DeepSeekLLM
from .gemini_llm import GeminiLLM
from .qwen_llm import QwenLLM