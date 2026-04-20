from .openai_llm import OpenAILLM
from . import LLMSettings


class GeminiLLM(OpenAILLM):
    def __init__(self, settings: LLMSettings):
        # Override base_url for Gemini
        settings.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        super().__init__(settings)