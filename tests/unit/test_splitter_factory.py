import pytest
from src.libs.splitter import (
    BaseSplitter,
    Chunk,
    SplitterSettings,
    SplitterFactory,
    RecursiveCharacterSplitter,
)


class TestChunkDataClass:
    """Test suite for Chunk data class."""

    def test_chunk_creation_success(self):
        """Test creating a valid Chunk."""
        chunk = Chunk(
            chunk_id="chunk_001",
            content="Sample text content",
            source="test.md",
            chunk_index=0,
            start_offset=0,
            end_offset=19,
        )
        assert chunk.chunk_id == "chunk_001"
        assert chunk.content == "Sample text content"
        assert chunk.chunk_index == 0
        assert chunk.metadata == {}

    def test_chunk_with_metadata(self):
        """Test creating a Chunk with metadata."""
        metadata = {"page": 1, "section": "Introduction"}
        chunk = Chunk(
            chunk_id="chunk_002",
            content="Content with metadata",
            source="test.md",
            chunk_index=1,
            start_offset=20,
            end_offset=41,
            metadata=metadata,
        )
        assert chunk.metadata == metadata
        assert chunk.metadata["page"] == 1

    def test_chunk_invalid_offset_range(self):
        """Test that invalid offset ranges raise ValueError."""
        with pytest.raises(ValueError, match="end_offset"):
            Chunk(
                chunk_id="chunk_003",
                content="Invalid",
                source="test.md",
                chunk_index=0,
                start_offset=100,
                end_offset=50,  # end < start
            )

    def test_chunk_empty_content_raises_error(self):
        """Test that empty content raises ValueError."""
        with pytest.raises(ValueError, match="content cannot be empty"):
            Chunk(
                chunk_id="chunk_004",
                content="",
                source="test.md",
                chunk_index=0,
                start_offset=0,
                end_offset=0,
            )


class TestSplitterSettings:
    """Test suite for SplitterSettings."""

    def test_settings_creation_with_defaults(self):
        """Test creating settings with default values."""
        settings = SplitterSettings(strategy="recursive")
        assert settings.strategy == "recursive"
        assert settings.chunk_size == 1000
        assert settings.chunk_overlap == 200
        assert settings.preserve_separators is True

    def test_settings_custom_values(self):
        """Test creating settings with custom values."""
        settings = SplitterSettings(
            strategy="semantic",
            chunk_size=2000,
            chunk_overlap=400,
            separator_chars=["\n\n", "\n"],
            preserve_separators=False,
        )
        assert settings.chunk_size == 2000
        assert settings.chunk_overlap == 400
        assert settings.separator_chars == ["\n\n", "\n"]
        assert settings.preserve_separators is False


class TestBaseSplitterValidation:
    """Test suite for BaseSplitter validation."""

    def test_base_splitter_cannot_instantiate(self):
        """Test that BaseSplitter is abstract and cannot be instantiated."""
        settings = SplitterSettings(strategy="test", chunk_size=1000)
        with pytest.raises(TypeError):
            BaseSplitter(settings)

    def test_settings_invalid_chunk_size(self):
        """Test that negative chunk_size raises ValueError."""
        settings = SplitterSettings(strategy="recursive", chunk_size=-100)
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            RecursiveCharacterSplitter(settings)

    def test_settings_invalid_chunk_overlap(self):
        """Test that overlap >= size raises ValueError."""
        settings = SplitterSettings(strategy="recursive", chunk_size=100, chunk_overlap=100)
        with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
            RecursiveCharacterSplitter(settings)


class TestRecursiveCharacterSplitter:
    """Test suite for RecursiveCharacterSplitter implementation."""

    def test_splitter_creation(self):
        """Test creating a RecursiveCharacterSplitter."""
        settings = SplitterSettings(strategy="recursive", chunk_size=100, chunk_overlap=20)
        splitter = RecursiveCharacterSplitter(settings)
        assert splitter.settings.strategy == "recursive"
        assert splitter.settings.chunk_size == 100

    def test_split_simple_text(self):
        """Test splitting simple text."""
        settings = SplitterSettings(strategy="recursive", chunk_size=50, chunk_overlap=10)
        splitter = RecursiveCharacterSplitter(settings)

        text = "This is a sample text. " * 5  # Long enough to require splitting
        source = "test.md"

        chunks = splitter.split(text, source)

        assert len(chunks) > 0
        assert all(isinstance(chunk, Chunk) for chunk in chunks)
        assert all(chunk.source == source for chunk in chunks)
        assert all(chunk.content.strip() for chunk in chunks)

    def test_split_with_metadata(self):
        """Test splitting with metadata."""
        settings = SplitterSettings(strategy="recursive", chunk_size=50, chunk_overlap=10)
        splitter = RecursiveCharacterSplitter(settings)

        text = "Sample text for testing splitting functionality. " * 3
        metadata = {"page": 1, "doc_type": "markdown"}

        chunks = splitter.split(text, "test.md", metadata)

        assert len(chunks) > 0
        assert all("page" in chunk.metadata for chunk in chunks)
        assert all(chunk.metadata["page"] == 1 for chunk in chunks)

    def test_split_empty_text_raises_error(self):
        """Test that splitting empty text raises ValueError."""
        settings = SplitterSettings(strategy="recursive", chunk_size=100, chunk_overlap=20)
        splitter = RecursiveCharacterSplitter(settings)

        with pytest.raises(ValueError, match="empty"):
            splitter.split("", "test.md")

    def test_split_whitespace_only_raises_error(self):
        """Test that splitting whitespace-only text raises ValueError."""
        settings = SplitterSettings(strategy="recursive", chunk_size=100, chunk_overlap=20)
        splitter = RecursiveCharacterSplitter(settings)

        with pytest.raises(ValueError, match="empty"):
            splitter.split("   \n\t  ", "test.md")

    def test_chunk_indexing(self):
        """Test that chunks have proper sequential indexing."""
        settings = SplitterSettings(strategy="recursive", chunk_size=30, chunk_overlap=5)
        splitter = RecursiveCharacterSplitter(settings)

        text = "This is test text. " * 10
        chunks = splitter.split(text, "test.md")

        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_id_generation(self):
        """Test that chunk IDs are stable and unique."""
        settings = SplitterSettings(strategy="recursive", chunk_size=50, chunk_overlap=10)
        splitter = RecursiveCharacterSplitter(settings)

        text = "Repeating text. " * 10
        chunks1 = splitter.split(text, "test.md")
        chunks2 = splitter.split(text, "test.md")

        # Same source and text should generate same IDs
        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1.chunk_id == c2.chunk_id

    def test_chunk_position_tracking(self):
        """Test that chunk positions are correctly tracked."""
        settings = SplitterSettings(strategy="recursive", chunk_size=100, chunk_overlap=20)
        splitter = RecursiveCharacterSplitter(settings)

        text = "Chapter 1. Introduction\n\nThis is the introduction section.\n\nChapter 2. Methods"
        chunks = splitter.split(text, "test.md")

        # Each chunk should have valid position tracking
        for chunk in chunks:
            assert chunk.start_offset >= 0
            assert chunk.end_offset > chunk.start_offset
            # Position should reference text content
            assert chunk.content in text or text.find(chunk.content) != -1


class TestSplitterFactory:
    """Test suite for SplitterFactory."""

    def test_factory_create_recursive_splitter(self):
        """Test factory creates RecursiveCharacterSplitter."""
        settings = SplitterSettings(strategy="recursive", chunk_size=1000)
        splitter = SplitterFactory.create(settings)
        assert isinstance(splitter, RecursiveCharacterSplitter)

    def test_factory_case_insensitive_strategy(self):
        """Test that strategy name is case-insensitive."""
        settings_upper = SplitterSettings(strategy="RECURSIVE", chunk_size=1000)
        settings_lower = SplitterSettings(strategy="recursive", chunk_size=1000)

        splitter_upper = SplitterFactory.create(settings_upper)
        splitter_lower = SplitterFactory.create(settings_lower)

        assert type(splitter_upper) == type(splitter_lower)

    def test_factory_invalid_strategy(self):
        """Test that invalid strategy raises ValueError."""
        settings = SplitterSettings(strategy="invalid_strategy", chunk_size=1000)
        with pytest.raises(ValueError, match="Unsupported splitting strategy"):
            SplitterFactory.create(settings)

    def test_factory_list_strategies(self):
        """Test listing available strategies."""
        strategies = SplitterFactory.list_strategies()
        assert isinstance(strategies, list)
        assert "recursive" in strategies

    def test_factory_register_custom_strategy(self):
        """Test registering a custom splitter strategy."""

        class DummySplitter(BaseSplitter):
            def split(self, text, source, metadata=None):
                if not text or not text.strip():
                    raise ValueError("Cannot split empty text")
                return [
                    Chunk(
                        chunk_id="dummy_0",
                        content=text,
                        source=source,
                        chunk_index=0,
                        start_offset=0,
                        end_offset=len(text),
                        metadata=metadata or {},
                    )
                ]

        SplitterFactory.register_strategy("dummy", DummySplitter)
        assert "dummy" in SplitterFactory.list_strategies()

        settings = SplitterSettings(strategy="dummy", chunk_size=1000)
        splitter = SplitterFactory.create(settings)
        assert isinstance(splitter, DummySplitter)

        # Test the dummy splitter works
        chunks = splitter.split("Test content", "test.md")
        assert len(chunks) == 1
        assert chunks[0].content == "Test content"


class TestSplitterIntegration:
    """Integration tests for splitter components."""

    def test_full_markdown_document_splitting(self):
        """Test splitting a realistic Markdown document."""
        markdown_text = """# Title

## Section 1
This is the first section with some content.

More content here to make it longer.

## Section 2
This is the second section.

- Item 1
- Item 2
- Item 3

### Subsection 2.1
Additional details go here.
"""
        settings = SplitterSettings(strategy="recursive", chunk_size=150, chunk_overlap=30)
        splitter = SplitterFactory.create(settings)

        chunks = splitter.split(markdown_text, "document.md")

        assert len(chunks) > 1
        assert sum(len(c.content) for c in chunks) > len(markdown_text) - 100
        # Overlap means total is longer than original
        for chunk in chunks:
            assert len(chunk.content) <= settings.chunk_size + 50  # Allow some tolerance

    def test_splitter_chain_with_metadata(self):
        """Test splitter maintains metadata through multiple operations."""
        text = "Sample content. " * 20
        metadata = {"doc_id": "doc_123", "version": 1}

        settings = SplitterSettings(strategy="recursive", chunk_size=100, chunk_overlap=20)
        splitter = SplitterFactory.create(settings)

        chunks = splitter.split(text, "test.md", metadata)

        for chunk in chunks:
            assert chunk.metadata["doc_id"] == "doc_123"
            assert chunk.metadata["version"] == 1
