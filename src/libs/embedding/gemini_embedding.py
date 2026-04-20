from .openai_embedding import OpenAIEmbedding
from . import EmbeddingSettings


class GeminiEmbedding(OpenAIEmbedding):
    def __init__(self, settings: EmbeddingSettings):
        settings.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        super().__init__(settings)