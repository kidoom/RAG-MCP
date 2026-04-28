"""Vector store abstraction layer and factory."""

from .base_vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreSettings,
)
from .chroma_store import ChromaStore, decode_collection_name, encode_collection_name
from .vector_store_factory import VectorStoreFactory

__all__ = [
    "BaseVectorStore",
    "ChromaStore",
    "decode_collection_name",
    "encode_collection_name",
    "QueryResult",
    "VectorRecord",
    "VectorStoreFactory",
    "VectorStoreSettings",
]
