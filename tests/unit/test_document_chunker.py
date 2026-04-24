"""Unit tests for DocumentChunker.

Tests use a FakeSplitter to isolate DocumentChunker logic from external
dependencies. This ensures tests are fast, deterministic, and don't require
real LLM/Embedding services.
"""

import hashlib
import re
from typing import Any, Dict, List, Optional

import pytest

from core.types import Document, Chunk
from core.settings import IngestionSettings
from ingestion.chunking import DocumentChunker


# =============================================================================
# Fake Splitter for Testing (Isolation)
# =============================================================================

class FakeSplitter:
    """Fake splitter for testing DocumentChunker in isolation.

    Simulates text splitting without external dependencies.
    """

    def __init__(
        self,
        chunk_size: int = 100,
        chunk_overlap: int = 20,
        split_points: Optional[List[int]] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.split_points = split_points

    def split(
        self, text: str, source: str, metadata: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """Split text into fake chunks.

        If split_points is provided, splits at those positions.
        Otherwise, splits by chunk_size with overlap.
        """
        from dataclasses import dataclass

        @dataclass
        class FakeChunk:
            content: str
            source: str
            chunk_index: int
            start_offset: int
            end_offset: int
            metadata: Dict[str, Any]

        chunks = []

        if self.split_points:
            # Split at specific points
            start = 0
            for i, end in enumerate(self.split_points):
                chunk_text = text[start:end]
                chunks.append(
                    FakeChunk(
                        content=chunk_text,
                        source=source,
                        chunk_index=i,
                        start_offset=start,
                        end_offset=end,
                        metadata=metadata or {},
                    )
                )
                start = end - self.chunk_overlap
                if start >= end:
                    start = end
            # Add remaining text
            if start < len(text):
                chunks.append(
                    FakeChunk(
                        content=text[start:],
                        source=source,
                        chunk_index=len(chunks),
                        start_offset=start,
                        end_offset=len(text),
                        metadata=metadata or {},
                    )
                )
        else:
            # Simple chunking by size with overlap
            start = 0
            chunk_index = 0
            while start < len(text):
                end = min(start + self.chunk_size, len(text))
                chunk_text = text[start:end]
                chunks.append(
                    FakeChunk(
                        content=chunk_text,
                        source=source,
                        chunk_index=chunk_index,
                        start_offset=start,
                        end_offset=end,
                        metadata=metadata or {},
                    )
                )
                next_start = end - self.chunk_overlap
                # Ensure progress when the final slice is shorter than chunk_overlap
                if next_start <= start:
                    next_start = end
                start = next_start
                chunk_index += 1

        return chunks


class FakeSettings:
    """Fake settings for testing."""

    def __init__(
        self,
        splitter: str = "recursive",
        chunk_size: int = 100,
        chunk_overlap: int = 20,
    ):
        self.ingestion = IngestionSettings(
            splitter=splitter,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=100,
        )


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def sample_document() -> Document:
    """Create a sample document for testing."""
    return Document(
        id="doc_abc123",
        text="This is the first section. [IMAGE: img_001] This is the second section with more content. [IMAGE: img_002] This is the third section.",
        metadata={
            "source_path": "/docs/sample.pdf",
            "doc_type": "pdf",
            "title": "Sample Document",
            "images": [
                {
                    "id": "img_001",
                    "path": "/images/img_001.png",
                    "text_offset": 27,
                    "text_length": 16,
                    "page": 1,
                },
                {
                    "id": "img_002",
                    "path": "/images/img_002.png",
                    "text_offset": 78,
                    "text_length": 16,
                    "page": 1,
                },
            ],
        },
    )


@pytest.fixture
def simple_document() -> Document:
    """Create a simple document without images."""
    return Document(
        id="doc_simple",
        text="Hello world. This is a simple document.",
        metadata={
            "source_path": "/docs/simple.txt",
            "doc_type": "txt",
        },
    )


# =============================================================================
# ID Generation Tests
# =============================================================================


def test_generate_chunk_id_format():
    """Test chunk ID follows expected format: {doc_id}_{index:04d}_{hash_8chars}"""
    doc_id = "doc_abc123"
    index = 5
    text = "Sample chunk text for hashing"

    chunk_id = DocumentChunker._generate_chunk_id(doc_id, index, text)

    # Check format
    pattern = r"^doc_abc123_0005_[a-f0-9]{8}$"
    assert re.match(pattern, chunk_id), f"Chunk ID {chunk_id} doesn't match expected format"

    # Verify hash part
    expected_hash = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    expected_id = f"{doc_id}_{index:04d}_{expected_hash}"
    assert chunk_id == expected_id


def test_chunk_id_determinism():
    """Test that same inputs produce same chunk ID."""
    doc_id = "doc_test"
    index = 0
    text = "Test content"

    id1 = DocumentChunker._generate_chunk_id(doc_id, index, text)
    id2 = DocumentChunker._generate_chunk_id(doc_id, index, text)

    assert id1 == id2, "Chunk ID should be deterministic"


def test_chunk_id_uniqueness():
    """Test that different indices produce different IDs."""
    doc_id = "doc_test"
    text = "Same text"

    id1 = DocumentChunker._generate_chunk_id(doc_id, 0, text)
    id2 = DocumentChunker._generate_chunk_id(doc_id, 1, text)

    assert id1 != id2, "Different indices should produce different IDs"


# =============================================================================
# Metadata Inheritance Tests
# =============================================================================


def test_metadata_inheritance(monkeypatch, simple_document):
    """Test that chunk metadata inherits all document metadata fields."""

    # Patch SplitterFactory to use FakeSplitter
    def mock_create(settings):
        return FakeSplitter(chunk_size=20, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    settings = FakeSettings(chunk_size=20, chunk_overlap=5)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(simple_document)

    # Verify all chunks have inherited metadata
    for chunk in chunks:
        assert chunk.metadata["source_path"] == "/docs/simple.txt"
        assert chunk.metadata["doc_type"] == "txt"
        assert "chunk_index" in chunk.metadata
        assert chunk.metadata["parent_doc_id"] == simple_document.id


def test_chunk_index_sequence(monkeypatch, simple_document):
    """Test that chunks have sequential indices starting from 0."""

    def mock_create(settings):
        return FakeSplitter(chunk_size=15, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    settings = FakeSettings(chunk_size=15, chunk_overlap=5)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(simple_document)

    # Verify sequential indices
    for i, chunk in enumerate(chunks):
        assert chunk.metadata["chunk_index"] == i


def test_source_ref_links_to_document(monkeypatch, simple_document):
    """Test that chunk.source_ref points to parent document ID."""

    def mock_create(settings):
        return FakeSplitter(chunk_size=20, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    settings = FakeSettings(chunk_size=20, chunk_overlap=5)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(simple_document)

    for chunk in chunks:
        assert chunk.source_ref == simple_document.id


def test_doc_type_extraction_from_source_path(monkeypatch):
    """Test that doc_type is extracted from source_path extension."""

    def mock_create(settings):
        return FakeSplitter(chunk_size=20, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    doc = Document(
        id="doc_test",
        text="Test content here. More content.",
        metadata={
            "source_path": "/docs/document.md",
        },
    )

    settings = FakeSettings(chunk_size=20, chunk_overlap=5)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(doc)

    for chunk in chunks:
        assert chunk.metadata.get("doc_type") == "md"


# =============================================================================
# Image Distribution Tests
# =============================================================================


def test_image_distribution_to_chunks(monkeypatch, sample_document):
    """Test that images are distributed to chunks containing their placeholders."""

    # Create splitter with specific split points to control which chunk gets which image
    def mock_create(settings):
        # Split so that first chunk contains img_001, second contains img_002
        return FakeSplitter(
            chunk_size=100,
            chunk_overlap=0,
            split_points=[50, 100],  # Split after positions 50 and 100
        )

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    settings = FakeSettings()
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(sample_document)

    # Find chunks with images
    chunks_with_images = [c for c in chunks if "images" in c.metadata]

    # At least one chunk should have images
    assert len(chunks_with_images) > 0, "Some chunks should contain images"

    # Verify image_refs field matches images
    for chunk in chunks_with_images:
        if "images" in chunk.metadata:
            image_ids = [img["id"] for img in chunk.metadata["images"]]
            assert chunk.metadata["image_refs"] == image_ids


def test_no_images_field_when_no_placeholders(monkeypatch):
    """Test that chunks without image placeholders don't have 'images' field."""

    def mock_create(settings):
        return FakeSplitter(chunk_size=20, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    # Document with images in metadata but no placeholders in first chunk
    doc = Document(
        id="doc_test",
        text="First part without images. Second part [IMAGE: img_001] with image.",
        metadata={
            "source_path": "/docs/test.pdf",
            "images": [
                {"id": "img_001", "path": "/images/img_001.png", "text_offset": 50, "text_length": 16},
            ],
        },
    )

    settings = FakeSettings(chunk_size=20, chunk_overlap=5)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(doc)

    # First chunk should not have images field
    first_chunk = chunks[0]
    if "[IMAGE:" not in first_chunk.text:
        assert "images" not in first_chunk.metadata, "Chunk without placeholders should not have 'images' field"


def test_image_refs_list_matches_placeholders(monkeypatch):
    """Test that image_refs list exactly matches placeholders in chunk text."""

    def mock_create(settings):
        return FakeSplitter(chunk_size=100, chunk_overlap=0)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    doc = Document(
        id="doc_test",
        text="Text with [IMAGE: img_001] and [IMAGE: img_002] two images.",
        metadata={
            "source_path": "/docs/test.pdf",
            "images": [
                {"id": "img_001", "path": "/images/img_001.png", "text_offset": 10, "text_length": 16},
                {"id": "img_002", "path": "/images/img_002.png", "text_offset": 30, "text_length": 16},
            ],
        },
    )

    settings = FakeSettings(chunk_size=100, chunk_overlap=0)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(doc)

    # Find chunk with images
    for chunk in chunks:
        if "images" in chunk.metadata:
            # Verify image_refs matches the placeholder IDs
            assert set(chunk.metadata["image_refs"]) == {"img_001", "img_002"}
            assert len(chunk.metadata["images"]) == 2


# =============================================================================
# Chunk Type Contract Tests
# =============================================================================


def test_chunk_serialization(monkeypatch, simple_document):
    """Test that chunks can be serialized and deserialized."""

    def mock_create(settings):
        return FakeSplitter(chunk_size=20, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    settings = FakeSettings(chunk_size=20, chunk_overlap=5)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(simple_document)

    for chunk in chunks:
        # Test to_dict
        chunk_dict = chunk.to_dict()
        assert "id" in chunk_dict
        assert "text" in chunk_dict
        assert "metadata" in chunk_dict
        assert "start_offset" in chunk_dict
        assert "end_offset" in chunk_dict
        assert "source_ref" in chunk_dict

        # Test from_dict roundtrip
        restored = Chunk.from_dict(chunk_dict)
        assert restored.id == chunk.id
        assert restored.text == chunk.text
        assert restored.source_ref == chunk.source_ref


def test_chunk_id_unique_per_document(monkeypatch):
    """Test that chunk IDs are unique within a document."""

    def mock_create(settings):
        return FakeSplitter(chunk_size=10, chunk_overlap=2)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create)

    doc = Document(
        id="doc_test",
        text="a b c d e f g h i j k l m n o p q r s t",
        metadata={"source_path": "/docs/test.txt"},
    )

    settings = FakeSettings(chunk_size=10, chunk_overlap=2)
    chunker = DocumentChunker(settings)

    chunks = chunker.split_document(doc)

    # All IDs should be unique
    ids = [chunk.id for chunk in chunks]
    assert len(ids) == len(set(ids)), "Chunk IDs must be unique within document"


# =============================================================================
# Configuration-Driven Tests
# =============================================================================


def test_chunk_size_affects_chunk_count(monkeypatch):
    """Test that changing chunk_size affects number of chunks produced."""

    doc = Document(
        id="doc_test",
        text="word " * 100,  # 500 chars total
        metadata={"source_path": "/docs/test.txt"},
    )

    # Small chunk size
    def mock_create_small(settings):
        return FakeSplitter(chunk_size=50, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create_small)

    settings_small = FakeSettings(chunk_size=50, chunk_overlap=5)
    chunker_small = DocumentChunker(settings_small)
    chunks_small = chunker_small.split_document(doc)

    # Large chunk size
    def mock_create_large(settings):
        return FakeSplitter(chunk_size=200, chunk_overlap=5)

    monkeypatch.setattr("ingestion.chunking.document_chunker.SplitterFactory.create", mock_create_large)

    settings_large = FakeSettings(chunk_size=200, chunk_overlap=5)
    chunker_large = DocumentChunker(settings_large)
    chunks_large = chunker_large.split_document(doc)

    # Smaller chunk size should produce more chunks
    assert len(chunks_small) > len(chunks_large)


# =============================================================================
# Error Handling Tests
# =============================================================================


def test_empty_document_text_raises_error():
    """Test that empty document text raises ValueError."""

    doc = Document(
        id="doc_empty",
        text="",
        metadata={"source_path": "/docs/empty.txt"},
    )

    # Create minimal settings
    settings = FakeSettings()

    # Need to patch the factory to avoid actual splitter initialization
    import ingestion.chunking.document_chunker as dcmodule
    original_create = dcmodule.SplitterFactory.create
    dcmodule.SplitterFactory.create = lambda s: FakeSplitter()

    try:
        chunker = DocumentChunker(settings)
        with pytest.raises(ValueError, match="empty"):
            chunker.split_document(doc)
    finally:
        dcmodule.SplitterFactory.create = original_create


def test_settings_without_ingestion_raises_error():
    """Test that Settings without ingestion config raises ValueError."""

    class EmptySettings:
        pass

    settings = EmptySettings()
    settings.ingestion = None

    with pytest.raises(ValueError, match="ingestion"):
        DocumentChunker(settings)
