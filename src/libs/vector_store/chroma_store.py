"""Chroma vector store provider implementation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base_vector_store import BaseVectorStore, QueryResult, VectorRecord, VectorStoreSettings

try:
    import chromadb
except ImportError as exc:  # pragma: no cover - environment dependent
    raise ImportError(
        "chromadb is required for ChromaStore. Install project dependencies first."
    ) from exc


class ChromaStore(BaseVectorStore):
    """Vector store implementation backed by ChromaDB persistent collections."""

    def __init__(self, settings: VectorStoreSettings):
        super().__init__(settings)
        self._client = chromadb.PersistentClient(path=settings.persist_directory)
        self._collection = self._client.get_or_create_collection(name=settings.collection_name)

    def upsert(self, records: List[VectorRecord], trace: Optional[Any] = None) -> None:
        if not records:
            return

        ids: List[str] = []
        embeddings: List[List[float]] = []
        documents: List[str] = []
        metadatas: List[Dict[str, Any]] = []

        for record in records:
            if not record.id:
                raise ValueError("VectorRecord.id cannot be empty")
            if not record.vector:
                raise ValueError("VectorRecord.vector cannot be empty")

            ids.append(record.id)
            embeddings.append(record.vector)
            documents.append(record.text)
            metadatas.append(record.metadata or {})

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        vector: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[Any] = None,
    ) -> List[QueryResult]:
        if not vector:
            raise ValueError("query vector cannot be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        response = self._collection.query(
            query_embeddings=[vector],
            n_results=top_k,
            where=filters if filters else None,
        )

        ids = response.get("ids", [[]])[0]
        documents = response.get("documents", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        distances = response.get("distances", [[]])[0]

        results: List[QueryResult] = []
        for item_id, text, metadata, distance in zip(ids, documents, metadatas, distances):
            # Chroma returns distance (lower is better). Convert to a bounded score.
            score = 1.0 / (1.0 + float(distance))
            results.append(
                QueryResult(
                    id=item_id,
                    score=score,
                    text=text or "",
                    metadata=metadata or {},
                )
            )
        return results
