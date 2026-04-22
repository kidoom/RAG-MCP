from .openai_llm import OpenAILLM
from .base_llm import LLMSettings


class DeepSeekLLM(OpenAILLM):
    def __init__(self, settings: LLMSettings):
        # DeepSeek uses OpenAI-compatible API
        super().__init__(settings)