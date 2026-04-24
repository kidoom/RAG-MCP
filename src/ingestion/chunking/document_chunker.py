"""Document chunking adapter that converts Documents to Chunks using libs.splitter.

This module provides DocumentChunker, which serves as an adapter layer between
the low-level libs.splitter and the Ingestion Pipeline. It handles:
- Document → Chunks conversion
- Stable chunk ID generation
- Metadata inheritance and image reference distribution
- Type conversion from libs.splitter.Chunk to core.types.Chunk
"""

# DocumentChunker 类实现了 Document 到 Chunk 的转换，包括稳定 ID 生成、元数据继承和图片引用分发。它使用 libs.splitter 进行文本切分，并转换为 core.types.Chunk 对象。
import hashlib
import re
from typing import Any, Dict, List, Set

from core.settings import Settings
from core.types import Chunk, Document
from libs.splitter import SplitterFactory, SplitterSettings


class DocumentChunker:
    """Adapter that splits Documents into Chunks using configured splitter.

    DocumentChunker adds business logic on top of libs.splitter:
    1. Generates stable, deterministic chunk IDs
    2. Inherits and extends Document metadata for each chunk
    3. Tracks chunk index and source reference (source_ref → Document.id)
    4. Distributes image references to chunks based on placeholder scanning
    5. Converts libs.splitter.Chunk to core.types.Chunk

    Example:
        >>> from core.settings import load_settings
        >>> from core.types import Document
        >>> settings = load_settings()
        >>> chunker = DocumentChunker(settings)
        >>> doc = Document(
        ...     id="doc_123",
        ...     text="Hello world! [IMAGE: img_001] More text.",
        ...     metadata={
        ...         "source_path": "/docs/example.pdf",
        ...         "doc_type": "pdf",
        ...         "images": [
        ...             {"id": "img_001", "path": "/images/img_001.png",
        ...              "text_offset": 12, "text_length": 16}
        ...         ]
        ...     }
        ... )
        >>> chunks = chunker.split_document(doc)
        >>> len(chunks) > 0
        True
        >>> chunks[0].source_ref == "doc_123"
        True
    """

    def __init__(self, settings: Settings):
        """Initialize DocumentChunker with settings.

        Args:
            settings: Application settings containing ingestion configuration.
                     Must have 'ingestion' field with splitter, chunk_size,
                     and chunk_overlap settings.

        Raises:
            ValueError: If settings.ingestion is None or missing required fields.
        """
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' configuration")

        self._settings = settings

        # Create splitter settings from ingestion config
        splitter_settings = SplitterSettings(
            strategy=settings.ingestion.splitter,
            chunk_size=settings.ingestion.chunk_size,
            chunk_overlap=settings.ingestion.chunk_overlap,
        )

        # Initialize splitter via factory
        self._splitter = SplitterFactory.create(splitter_settings)

    def split_document(self, document: Document) -> List[Chunk]:
        """Split a Document into Chunks.

        Args:
            document: Document to split. Must have valid metadata with
                     source_path field.

        Returns:
            List of Chunk objects with proper IDs, metadata, and image refs.

        Raises:
            ValueError: If document.text is empty or metadata is invalid.
        """
        if not document.text or not document.text.strip():
            raise ValueError("Cannot split document with empty text")

        # Use libs.splitter to split text
        source_path = document.metadata.get("source_path", document.id)
        lib_chunks = self._splitter.split(
            text=document.text,
            source=source_path,
            metadata=document.metadata,
        )

        # Convert libs.splitter.Chunk to core.types.Chunk
        result: List[Chunk] = []

        for chunk_index, lib_chunk in enumerate(lib_chunks):
            # Generate stable chunk ID
            chunk_id = self._generate_chunk_id(
                document.id, chunk_index, lib_chunk.content
            )

            # Build metadata with inheritance and chunk-specific fields
            chunk_metadata = self._inherit_metadata(
                document, chunk_index, lib_chunk.content
            )

            # Create core.types.Chunk
            chunk = Chunk(
                id=chunk_id,
                text=lib_chunk.content,
                metadata=chunk_metadata,
                start_offset=lib_chunk.start_offset,
                end_offset=lib_chunk.end_offset,
                source_ref=document.id,
            )
            result.append(chunk)

        return result

    @staticmethod
    def _generate_chunk_id(doc_id: str, index: int, text: str) -> str:
        """Generate stable, deterministic chunk ID.

        Format: {doc_id}_{index:04d}_{hash_8chars}

        Args:
            doc_id: Parent document ID
            index: Chunk index within document (0-based)
            text: Chunk text content (for hash generation)

        Returns:
            Unique, deterministic chunk ID string
        """
        content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
        return f"{doc_id}_{index:04d}_{content_hash}"

    def _inherit_metadata(
        self, document: Document, chunk_index: int, chunk_text: str
    ) -> Dict[str, Any]:
        # 构建 chunk 元数据，继承自 document 并添加 chunk-specific 字段。
        """Build chunk metadata by inheriting from document and adding chunk-specific fields.

        Args:
            document: Source document
            chunk_index: Index of this chunk in the document
            chunk_text: Text content of this chunk (for image placeholder scanning)

        Returns:
            Dictionary containing inherited metadata plus chunk-specific fields
        """
        # Start with a copy of document metadata; never copy doc-level ``images``
        # wholesale (C4): only attach per-chunk subsets derived from placeholders.
        metadata = {**document.metadata}
        metadata.pop("images", None)

        # Add chunk-specific fields
        metadata["chunk_index"] = chunk_index
        metadata["parent_doc_id"] = document.id

        # Infer doc_type from extension only when Loader did not set it
        source_path = metadata.get("source_path", "")
        if "doc_type" not in metadata and source_path and "." in source_path:
            parts = source_path.rsplit(".", 1)
            if len(parts) == 2:
                metadata["doc_type"] = parts[1].lower()

        # Distribute image references to this chunk
        chunk_images = self._extract_chunk_images(document, chunk_text)
        if chunk_images:
            metadata["images"] = chunk_images
            metadata["image_refs"] = [img["id"] for img in chunk_images]

        return metadata

    def _extract_chunk_images(
        self, document: Document, chunk_text: str
    ) -> List[Dict[str, Any]]:
        """Extract image references that belong to this chunk.

        Scans chunk_text for [IMAGE: {id}] placeholders and returns only the
        images from document.metadata["images"] that are referenced in this chunk.

        Args:
            document: Source document containing full images list in metadata
            chunk_text: Text of this chunk to scan for image placeholders

        Returns:
            List of image metadata dicts referenced by this chunk (may be empty)
        """
        # Get document-level images list
        doc_images = document.metadata.get("images", [])
        if not doc_images:
            return []

        # Find all [IMAGE: {id}] placeholders in chunk text
        pattern = r"\[IMAGE:\s*([^\]]+)\]"
        matches = re.findall(pattern, chunk_text)
        referenced_ids: Set[str] = set(matches)

        if not referenced_ids:
            return []

        # Filter document images to only those referenced in this chunk
        chunk_images: List[Dict[str, Any]] = []
        for img in doc_images:
            if isinstance(img, dict) and img.get("id") in referenced_ids:
                chunk_images.append(dict(img))  # Copy to avoid mutation

        return chunk_images
