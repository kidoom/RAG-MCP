from typing import List
from openai import OpenAI
from . import BaseEmbedding, EmbeddingSettings

# Per-provider API limits (e.g. Qwen dashscope allows max 10 inputs per call).
_DEFAULT_EMBED_MAX_BATCH = 10


class OpenAIEmbedding(BaseEmbedding):
    def __init__(self, settings: EmbeddingSettings, *, embed_max_batch: int | None = None):
        super().__init__(settings)
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
        )
        self._embed_max_batch = (
            embed_max_batch if embed_max_batch is not None else _DEFAULT_EMBED_MAX_BATCH
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if len(texts) <= self._embed_max_batch:
            response = self.client.embeddings.create(
                model=self.settings.model,
                input=texts,
            )
            return [data.embedding for data in response.data]

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), self._embed_max_batch):
            chunk = texts[i : i + self._embed_max_batch]
            response = self.client.embeddings.create(
                model=self.settings.model,
                input=chunk,
            )
            all_embeddings.extend(data.embedding for data in response.data)
        return all_embeddings

    def embed_query(self, query: str) -> List[float]:
        response = self.client.embeddings.create(
            model=self.settings.model,
            input=[query],
        )
        return response.data[0].embedding