from typing import Dict, Type
from .base_llm import BaseLLM, LLMSettings
from .base_vision_llm import BaseVisionLLM, VisionLLMSettings
from .openai_llm import OpenAILLM
from .azure_llm import AzureLLM
from .ollama_llm import OllamaLLM
from .deepseek_llm import DeepSeekLLM
from .gemini_llm import GeminiLLM
from .qwen_llm import QwenLLM
from .vision_llm.openai_vision_llm import OpenAIVisionLLM
from .vision_llm.azure_vision_llm import AzureVisionLLM
from .vision_llm.ollama_vision_llm import OllamaVisionLLM
from .vision_llm.qwen_vision_llm import QwenVisionLLM
from .vision_llm.gemini_vision_llm import GeminiVisionLLM


class LLMFactory:
    """Factory class for creating LLM and Vision LLM instances."""

    _llm_providers: Dict[str, Type[BaseLLM]] = {
        "openai": OpenAILLM,
        "azure": AzureLLM,
        "ollama": OllamaLLM,
        "deepseek": DeepSeekLLM,
        "gemini": GeminiLLM,
        "qwen": QwenLLM,
    }

    _vision_llm_providers: Dict[str, Type[BaseVisionLLM]] = {
        "openai": OpenAIVisionLLM,
        "azure": AzureVisionLLM,
        "ollama": OllamaVisionLLM,
        "qwen": QwenVisionLLM,
        "gemini": GeminiVisionLLM,
    }

    @classmethod
    def create_llm(cls, settings: LLMSettings) -> BaseLLM:
        """Create an LLM instance based on the provider in settings."""
        provider_name = settings.provider.lower()
        provider_cls = cls._llm_providers.get(provider_name)

        if not provider_cls:
            raise ValueError(f"Unsupported LLM provider: {provider_name}")

        return provider_cls(settings)

    @classmethod
    def create_vision_llm(cls, settings: VisionLLMSettings) -> BaseVisionLLM:
        """Create a Vision LLM instance based on the provider in settings."""
        provider_name = settings.provider.lower()
        provider_cls = cls._vision_llm_providers.get(provider_name)

        if not provider_cls:
            raise ValueError(f"Unsupported Vision LLM provider: {provider_name}")

        return provider_cls(settings)

    @classmethod
    def register_llm_provider(cls, name: str, provider_cls: Type[BaseLLM]):
        """Register a new LLM provider."""
        cls._llm_providers[name.lower()] = provider_cls

    @classmethod
    def register_vision_llm_provider(cls, name: str, provider_cls: Type[BaseVisionLLM]):
        """Register a new Vision LLM provider."""
        cls._vision_llm_providers[name.lower()] = provider_cls
