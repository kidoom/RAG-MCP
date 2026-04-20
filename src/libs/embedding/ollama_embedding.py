from typing import List
from openai import OpenAI
from . import BaseEmbedding, EmbeddingSettings


class OllamaEmbedding(BaseEmbedding):
    def __init__(self, settings: EmbeddingSettings):
        super().__init__(settings)
        self.client = OpenAI(
            base_url=settings.base_url or "http://localhost:11434/v1",
            api_key="ollama"
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