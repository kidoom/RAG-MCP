"""Vector store abstraction layer and factory."""

from .base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreSettings,
)
from .chroma_store import ChromaStore
from .vector_store_factory import VectorStoreFactory

__all__ = [
    "BaseVectorStore",
    "ChromaStore",
    "QueryResult",
    "VectorRecord",
    "VectorStoreFactory",
    "VectorStoreSettings",
]
