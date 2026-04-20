from .openai_embedding import OpenAIEmbedding
from . import EmbeddingSettings


class QwenEmbedding(OpenAIEmbedding):
    def __init__(self, settings: EmbeddingSettings):
        settings.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        super().__init__(settings)