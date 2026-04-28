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

import json


def _sanitize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Filter metadata to only ChromaDB-compatible types (str, int, float, bool).

    Lists are serialized to JSON strings. Dicts and other complex values are skipped.
    """
    clean: Dict[str, Any] = {}
    for key, value in meta.items():
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
        elif isinstance(value, list):
            clean[key] = json.dumps(value, ensure_ascii=False)
        # skip dict, None, and other non-primitive types
    return clean


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
            metadatas.append(_sanitize_metadata(record.metadata or {}))

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

    def get_by_ids(
        self,
        ids: List[str],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        normalized_ids = [str(item).strip() for item in ids if str(item).strip()]
        if not normalized_ids:
            return []

        response = self._collection.get(
            ids=normalized_ids,
            include=["documents", "metadatas"],
        )
        out_ids = response.get("ids") or []
        documents = response.get("documents") or []
        metadatas = response.get("metadatas") or []

        results: List[Dict[str, Any]] = []
        for item_id, text, metadata in zip(out_ids, documents, metadatas):
            results.append(
                {
                    "id": str(item_id),
                    "text": text or "",
                    "metadata": metadata or {},
                }
            )
        return results

    def get_by_metadata(
        self,
        filters: Dict[str, Any],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch records matching a metadata filter.

        Uses ChromaDB's ``get(where=...)`` which supports $eq, $in, $and, etc.
        Empty filters returns all records.
        """
        kwargs: Dict[str, Any] = {"include": ["documents", "metadatas"]}
        if filters:
            kwargs["where"] = filters
        response = self._collection.get(**kwargs)
        out_ids = response.get("ids") or []
        documents = response.get("documents") or []
        metadatas = response.get("metadatas") or []

        results: List[Dict[str, Any]] = []
        for item_id, text, metadata in zip(out_ids, documents, metadatas):
            results.append(
                {
                    "id": str(item_id),
                    "text": text or "",
                    "metadata": metadata or {},
                }
            )
        return results

    def delete_by_metadata(
        self,
        filters: Dict[str, Any],
        trace: Optional[Any] = None,
    ) -> int:
        """Delete all records matching a metadata filter. Returns count deleted."""
        if not filters:
            return 0

        existing = self._collection.get(where=filters, include=[])
        ids_to_delete = existing.get("ids") or []
        if not ids_to_delete:
            return 0
        self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)

    def get_collection_stats(self, trace: Optional[Any] = None) -> Dict[str, Any]:
        """Return collection statistics."""
        return {
            "collection_name": self.settings.collection_name,
            "entry_count": self._collection.count(),
        }

    def get_all_collections(self) -> List[str]:
        """List all collection names in the persistent client."""
        return [c.name for c in self._client.list_collections()]
