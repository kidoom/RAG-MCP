"""
Ingestion module for Modular RAG MCP Server.

This module handles document ingestion, processing, and indexing
for the RAG system.
"""

from .chunking import DocumentChunker
from .embedding import BatchProcessor, DenseEncoder, SparseEncoder
from .pipeline import IngestionPipeline, IngestionPipelineError, IngestionResult
from .storage import BM25Indexer
from .transform import BaseTransform, ChunkRefiner, ImageCaptioner, MetadataEnricher

__version__ = "0.1.0"
__all__ = [
    "DocumentChunker",
    "BatchProcessor",
    "DenseEncoder",
    "SparseEncoder",
    "IngestionPipeline",
    "IngestionPipelineError",
    "IngestionResult",
    "BM25Indexer",
    "BaseTransform",
    "ChunkRefiner",
    "MetadataEnricher",
    "ImageCaptioner",
]