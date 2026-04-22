from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Union
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
    def chat_with_image(
        self,
        text: str,
        image_path: Optional[Union[str, bytes]] = None,
        **kwargs
    ) -> str:
        """Chat with an image and text."""
        pass

    @abstractmethod
    def describe_image(self, image_path: str, prompt: str = None) -> str:
        """Describe an image with optional prompt."""
        pass
