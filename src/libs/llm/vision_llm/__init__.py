from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class VisionLLMSettings:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    azure_endpoint: Optional[str] = None
    deployment_name: Optional[str] = None
    api_version: Optional[str] = None
    max_image_size: int = 2048
    enabled: bool = True


class BaseVisionLLM(ABC):
    def __init__(self, settings: VisionLLMSettings):
        self.settings = settings

    @abstractmethod
    def describe_image(self, image_path: str, prompt: str = None) -> str:
        """Describe an image with optional prompt"""
        pass

    @abstractmethod
    def describe_images(self, image_paths: List[str], prompt: str = None) -> List[str]:
        """Describe multiple images"""
        pass


# Provider registry
_vision_llm_providers = {}


def register_vision_llm_provider(provider_name: str, cls):
    _vision_llm_providers[provider_name] = cls


def get_vision_llm_provider(provider_name: str) -> type:
    return _vision_llm_providers.get(provider_name)


# Import providers
from .openai_vision_llm import OpenAIVisionLLM
from .azure_vision_llm import AzureVisionLLM
from .ollama_vision_llm import OllamaVisionLLM
from .qwen_vision_llm import QwenVisionLLM
from .gemini_vision_llm import GeminiVisionLLM