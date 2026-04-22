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
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """Chat with messages"""
        pass
