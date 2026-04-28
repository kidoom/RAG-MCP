"""Base abstractions for vector store implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VectorStoreSettings:
    """Configuration for vector store providers."""

    provider: str
    persist_directory: str
    collection_name: str = "default"


@dataclass
class VectorRecord:
    """Record payload for vector upsert operations."""

    id: str
    vector: List[float]
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryResult:
    """Normalized result shape returned by vector queries."""

    id: str
    score: float
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseVectorStore(ABC):
    """Abstract base class for all vector store providers."""

    def __init__(self, settings: VectorStoreSettings):
        self.settings = settings

    @abstractmethod
    def upsert(
        self,
        records: List[VectorRecord],
        trace: Optional[Any] = None,
    ) -> None:
        """Upsert vector records into the underlying store."""
        raise NotImplementedError

    @abstractmethod
    def query(
        self,
        vector: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        trace: Optional[Any] = None,
    ) -> List[QueryResult]:
        """Search for top-k nearest records matching query constraints."""
        raise NotImplementedError

    @abstractmethod
    def get_by_ids(
        self,
        ids: List[str],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch records by chunk IDs with text and metadata payload."""
        raise NotImplementedError
