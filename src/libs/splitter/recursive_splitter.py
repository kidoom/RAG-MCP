"""Recursive character text splitter implementation."""

import hashlib
from typing import List, Optional, Dict, Any

from . import BaseSplitter, Chunk, SplitterSettings


class RecursiveCharacterSplitter(BaseSplitter):
    """Splits text recursively using character separators.
    
    This implementation provides recursive character splitting with semantic
    boundary preservation, similar to LangChain's RecursiveCharacterTextSplitter,
    but implemented from scratch for better control and fewer dependencies.
    """

    def __init__(self, settings: SplitterSettings):
        """Initialize recursive character splitter.
        
        Args:
            settings: SplitterSettings with strategy='recursive'
        """
        super().__init__(settings)
        
        # Default separators for Markdown documents (ordered by semantic importance)
        if settings.separator_chars is None:
            self._separators = [
                "\n\n",          # Paragraph breaks
                "\n",            # Line breaks
                " ",             # Spaces
                "",              # Fall back to character level
            ]
        else:
            self._separators = settings.separator_chars

    def split(self, text: str, source: str, metadata: Optional[Dict[str, Any]] = None) -> List[Chunk]:
        """Split text using recursive character splitting.
        
        Args:
            text: Text to split (Markdown format recommended)
            source: Source identifier
            metadata: Optional metadata for all chunks
            
        Returns:
            List of Chunk objects with position tracking
            
        Raises:
            ValueError: If text is empty
        """
        if not text or not text.strip():
            raise ValueError("Cannot split empty or whitespace-only text")
        
        if metadata is None:
            metadata = {}
        
        # Split text into chunks
        chunk_texts = self._recursive_split(text)
        
        chunks = []
        current_offset = 0
        
        for chunk_index, chunk_text in enumerate(chunk_texts):
            # Find the position of this chunk in the original text
            # (accounting for potential overlaps in the splitter)
            start_offset = text.find(chunk_text, current_offset)
            
            if start_offset == -1:
                # Fallback: chunk might have been modified, estimate position
                start_offset = current_offset
            
            end_offset = start_offset + len(chunk_text)
            current_offset = end_offset - self.settings.chunk_overlap
            
            # Generate stable chunk ID based on content hash
            chunk_id = self._generate_chunk_id(source, chunk_index, chunk_text)
            
            chunk = Chunk(
                chunk_id=chunk_id,
                content=chunk_text,
                source=source,
                chunk_index=chunk_index,
                start_offset=start_offset,
                end_offset=end_offset,
                metadata={**metadata, "strategy": "recursive"}
            )
            chunks.append(chunk)
        
        return chunks

    def _recursive_split(self, text: str) -> List[str]:
        """Recursively split text using separators in order.
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        return self._split_with_separators(text, self._separators)

    def _split_with_separators(self, text: str, separators: List[str]) -> List[str]:
        """Split text using the given separators in order.
        
        Args:
            text: Text to split
            separators: List of separators to try in order
            
        Returns:
            List of text chunks
        """
        if not separators:
            # No more separators, return text as single chunk
            return [text] if text else []
        
        separator = separators[0]
        remaining_separators = separators[1:]
        
        if not separator:
            # Empty separator means character-level splitting
            return self._split_by_length(text)
        
        # Split by current separator
        parts = text.split(separator)
        
        # If we only have one part, try next separator
        if len(parts) == 1:
            return self._split_with_separators(text, remaining_separators)
        
        # Process each part recursively
        result = []
        for part in parts:
            if part:  # Skip empty parts
                if len(part) <= self.settings.chunk_size:
                    result.append(part)
                else:
                    # Part is still too long, split recursively
                    sub_parts = self._split_with_separators(part, remaining_separators)
                    result.extend(sub_parts)
        
        # Add back separators between chunks (except for the last one)
        if separator and result:
            result_with_separators = []
            for i, chunk in enumerate(result):
                if i < len(result) - 1:
                    result_with_separators.append(chunk + separator)
                else:
                    result_with_separators.append(chunk)
            result = result_with_separators
        
        # Apply chunk size limits and overlaps
        return self._apply_chunk_limits(result)

    def _split_by_length(self, text: str) -> List[str]:
        """Split text by character length when no separators work.
        
        Args:
            text: Text to split
            
        Returns:
            List of chunks within size limits
        """
        if len(text) <= self.settings.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + self.settings.chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - self.settings.chunk_overlap
            
            if start >= len(text):
                break
        
        return chunks

    def _apply_chunk_limits(self, chunks: List[str]) -> List[str]:
        """Apply chunk size limits and overlaps to chunks.
        
        Args:
            chunks: Initial chunks
            
        Returns:
            Chunks with proper size limits and overlaps
        """
        if not chunks:
            return chunks
        
        result = []
        current_chunk = ""
        
        for chunk in chunks:
            if not current_chunk:
                current_chunk = chunk
            elif len(current_chunk + chunk) <= self.settings.chunk_size:
                current_chunk += chunk
            else:
                # Current chunk is full, start new one with overlap
                if current_chunk:
                    result.append(current_chunk)
                # Start new chunk with overlap from previous
                overlap_start = max(0, len(current_chunk) - self.settings.chunk_overlap)
                current_chunk = current_chunk[overlap_start:] + chunk
        
        if current_chunk:
            result.append(current_chunk)
        
        return result

    @staticmethod
    def _generate_chunk_id(source: str, chunk_index: int, content: str) -> str:
        """Generate stable chunk ID based on source, index, and content hash.
        
        Args:
            source: Source identifier
            chunk_index: Position of chunk in document
            content: Chunk content
            
        Returns:
            Unique, deterministic chunk ID
        """
        content_hash = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"{source}#{chunk_index}#{content_hash}"
