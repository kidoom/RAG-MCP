from .openai_vision_llm import OpenAIVisionLLM
from . import VisionLLMSettings


class QwenVisionLLM(OpenAIVisionLLM):
    def __init__(self, settings: VisionLLMSettings):
        settings.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        super().__init__(settings)