"""MCP tool: list collections from the vector store."""

from __future__ import annotations

from typing import Any

from core.settings import load_settings
from libs.vector_store import VectorStoreFactory, VectorStoreSettings


def list_collections(arguments: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    store = VectorStoreFactory.create(
        VectorStoreSettings(
            provider=settings.vector_store.provider,
            persist_directory=settings.vector_store.persist_directory,
            collection_name=settings.vector_store.collection_name,
        )
    )
    collection_names = store.get_all_collections()
    markdown_lines = ["可用集合："] if collection_names else ["暂无可用集合。"]
    for idx, name in enumerate(collection_names, start=1):
        markdown_lines.append(f"{idx}. {name}")
    return {
        "content": [{"type": "text", "text": "\n".join(markdown_lines)}],
        "structuredContent": {"collections": collection_names},
    }
