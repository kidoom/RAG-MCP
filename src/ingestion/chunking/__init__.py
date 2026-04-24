"""Chunking module for document splitting.

This module provides DocumentChunker, which adapts libs.splitter to the
Ingestion Pipeline by converting Documents to Chunks with proper metadata
inheritance and image reference distribution.
"""

from .document_chunker import DocumentChunker

__all__ = ["DocumentChunker"]
