"""Splitter abstraction layer for text chunking strategies."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """Represents a text chunk from document splitting.
    
    Attributes:
        chunk_id: Unique identifier for the chunk
        content: The actual text content of the chunk
        source: Source document path/identifier
        chunk_index: Sequential index of this chunk within the document
        start_offset: Character offset where this chunk starts in the original document
        end_offset: Character offset where this chunk ends in the original document
        metadata: Additional metadata (page number, section, etc.)
    """
    chunk_id: str
    content: str
    source: str
    chunk_index: int
    start_offset: int
    end_offset: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate chunk data after initialization."""
        if self.end_offset < self.start_offset:
            raise ValueError(f"end_offset ({self.end_offset}) cannot be less than start_offset ({self.start_offset})")
        if len(self.content) == 0:
            raise ValueError("Chunk content cannot be empty")


@dataclass
class SplitterSettings:
    """Settings for text splitters.
    
    Attributes:
        strategy: Name of the splitting strategy (e.g., 'recursive', 'sentence', 'semantic')
        chunk_size: Target size for chunks (in characters or tokens)
        chunk_overlap: Number of characters/tokens to overlap between chunks
        separator_chars: Custom separator characters for splitting (strategy-dependent)
        preserve_separators: Whether to preserve separator characters in output chunks
    """
    strategy: str
    chunk_size: int = 1000
    chunk_overlap: int = 200
    separator_chars: Optional[List[str]] = None
    preserve_separators: bool = True


class BaseSplitter(ABC):
    """Abstract base class for text splitting strategies.
    
    All splitter implementations must inherit from this class and implement
    the split() method according to their specific strategy.
    """

    def __init__(self, settings: SplitterSettings):
        """Initialize splitter with settings.
        
        Args:
            settings: SplitterSettings instance containing configuration
            
        Raises:
            ValueError: If settings validation fails
        """
        self._validate_settings(settings)
        self.settings = settings

    @staticmethod
    def _validate_settings(settings: SplitterSettings) -> None:
        """Validate splitter settings.
        
        Args:
            settings: Settings to validate
            
        Raises:
            ValueError: If settings are invalid
        """
        if settings.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if settings.chunk_overlap < 0:
            raise ValueError("chunk_overlap cannot be negative")
        if settings.chunk_overlap >= settings.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

    @abstractmethod
    def split(self, text: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> List[Chunk]:
        """Split text into chunks using the implemented strategy.
        
        Args:
            text: The text to split (typically Markdown format)
            source: Source identifier (file path, document name, etc.)
            metadata: Optional metadata to attach to all chunks
            
        Returns:
            List of Chunk objects with proper indexing and offset information
            
        Raises:
            ValueError: If text is empty or invalid
        """
        pass


# Import implementations and factory
from .recursive_splitter import RecursiveCharacterSplitter
from .splitter_factory import SplitterFactory

__all__ = [
    "BaseSplitter",
    "Chunk",
    "SplitterSettings",
    "SplitterFactory",
    "RecursiveCharacterSplitter",
]

