"""Dense retriever implementation for semantic recall (D2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.settings import Settings
from core.types import RetrievalResult
from libs.embedding import (
    BaseEmbedding,
    EmbeddingFactory,
    EmbeddingSettings as LibEmbeddingSettings,
)
from libs.vector_store import (
    BaseVectorStore,
    VectorStoreFactory,
    VectorStoreSettings as LibVectorStoreSettings,
)


class DenseRetriever:
    """Run query embedding + vector search and normalize returned records."""

    def __init__(
        self,
        settings: Settings,
        embedding_client: Optional[BaseEmbedding] = None,
        vector_store: Optional[BaseVectorStore] = None,
    ) -> None:
        self._settings = settings
        self._embedding_client = embedding_client or EmbeddingFactory.create(
            LibEmbeddingSettings(
                provider=settings.embedding.provider,
                model=settings.embedding.model,
                dimensions=settings.embedding.dimensions,
                api_key=settings.embedding.api_key or None,
                base_url=settings.embedding.base_url or None,
                azure_endpoint=settings.embedding.azure_endpoint or None,
                deployment_name=settings.embedding.deployment_name or None,
                api_version=settings.embedding.api_version or None,
            )
        )
        self._vector_store = vector_store or VectorStoreFactory.create(
            LibVectorStoreSettings(
                provider=settings.vector_store.provider,
                persist_directory=settings.vector_store.persist_directory,
                collection_name=settings.vector_store.collection_name,
            )
        )

    def retrieve(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[Any] = None,
    ) -> List[RetrievalResult]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        query_vector = self._embedding_client.embed_query(query)
        raw_results = self._vector_store.query(
            vector=query_vector,
            top_k=top_k,
            filters=filters or None,
            trace=trace,
        )

        return [
            RetrievalResult(
                chunk_id=item.id,
                score=float(item.score),
                text=item.text or "",
                metadata=dict(item.metadata or {}),
            )
            for item in raw_results
        ]
