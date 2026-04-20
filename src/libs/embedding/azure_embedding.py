from typing import List
from openai import AzureOpenAI
from . import BaseEmbedding, EmbeddingSettings


class AzureEmbedding(BaseEmbedding):
    def __init__(self, settings: EmbeddingSettings):
        super().__init__(settings)
        self.client = AzureOpenAI(
            api_key=settings.api_key,
            azure_endpoint=settings.azure_endpoint,
            api_version=settings.api_version
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(
            model=self.settings.deployment_name,
            input=texts
        )
        return [data.embedding for data in response.data]

    def embed_query(self, query: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self.settings.deployment_name,
            input=[query]
        )
        return response.data[0].embedding