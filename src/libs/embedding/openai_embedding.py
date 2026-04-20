from typing import List
from openai import OpenAI
from . import BaseEmbedding, EmbeddingSettings


class OpenAIEmbedding(BaseEmbedding):
    def __init__(self, settings: EmbeddingSettings):
        super().__init__(settings)
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model=self.settings.model,
            input=texts
        )
        return [data.embedding for data in response.data]

    def embed_query(self, query: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self.settings.model,
            input=[query]
        )
        return response.data[0].embedding