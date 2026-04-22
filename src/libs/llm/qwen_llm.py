from .openai_llm import OpenAILLM
from .base_llm import LLMSettings


class QwenLLM(OpenAILLM):
    def __init__(self, settings: LLMSettings):
        # Override base_url for Qwen
        settings.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        super().__init__(settings)