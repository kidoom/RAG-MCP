"""Transform step abstraction for ingestion pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from core.types import Chunk
from core.trace.trace_context import TraceContext


class BaseTransform(ABC):
    """Atomic transform over a batch of chunks (may mutate text/metadata)."""

    @abstractmethod
    def transform(
        self, chunks: List[Chunk], trace: Optional[TraceContext] = None
    ) -> List[Chunk]:
        """Return refined chunks in stable order."""
