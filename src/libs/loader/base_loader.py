"""Base abstractions for document loaders."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from core.types import Document


class BaseLoader(ABC):
    """Abstract base class for all loader implementations."""

    @abstractmethod
    def load(self, path: str, trace: Optional[Any] = None) -> Document:
        """Load file content and return a normalized Document object."""
        raise NotImplementedError
