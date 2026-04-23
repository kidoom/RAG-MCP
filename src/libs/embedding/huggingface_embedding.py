from typing import List
from sentence_transformers import SentenceTransformer
from . import BaseEmbedding, EmbeddingSettings


class HuggingFaceEmbedding(BaseEmbedding):
    """Embedding provider using HuggingFace sentence-transformers models."""

    def __init__(self, settings: EmbeddingSettings):
        super().__init__(settings)
        self.model = SentenceTransformer(
            model_name_or_path=settings.model,
            device=settings.device
        )

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        embeddings = self.model.encode(texts)
        return embeddings.tolist()

    def embed_query(self, query: str) -> List[float]:
        embedding = self.model.encode([query])[0]
        return embedding.tolist()
