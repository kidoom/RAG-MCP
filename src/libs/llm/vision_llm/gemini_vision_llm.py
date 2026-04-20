from .openai_vision_llm import OpenAIVisionLLM
from . import VisionLLMSettings


class GeminiVisionLLM(OpenAIVisionLLM):
    def __init__(self, settings: VisionLLMSettings):
        settings.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        super().__init__(settings)