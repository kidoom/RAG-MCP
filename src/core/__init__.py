"""
Core module for Modular RAG MCP Server.

This module contains core functionality including configuration management,
logging, and shared utilities.
"""

from .types import (
    Chunk,
    ChunkRecord,
    Document,
    extract_image_ids_from_text,
    format_image_placeholder,
    IMAGE_PLACEHOLDER_TEMPLATE,
    to_json,
    validate_chunk_contract,
    validate_document_contract,
    validate_images_metadata,
    validate_metadata_source_path,
)

__all__ = [
    "Chunk",
    "ChunkRecord",
    "Document",
    "IMAGE_PLACEHOLDER_TEMPLATE",
    "extract_image_ids_from_text",
    "format_image_placeholder",
    "to_json",
    "validate_chunk_contract",
    "validate_document_contract",
    "validate_images_metadata",
    "validate_metadata_source_path",
]

__version__ = "0.1.0"