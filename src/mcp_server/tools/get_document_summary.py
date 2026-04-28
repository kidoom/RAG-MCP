"""MCP tool: get document summary by document identifier."""

from __future__ import annotations

from typing import Any, Dict, List

from libs.vector_store import VectorStoreFactory, VectorStoreSettings

from core.settings import load_settings


def _normalize_doc_id(value: Any) -> str:
    doc_id = str(value or "").strip()
    if not doc_id:
        raise ValueError("doc_id is required")
    return doc_id


def get_document_summary(arguments: Dict[str, Any]) -> Dict[str, Any]:
    doc_id = _normalize_doc_id(arguments.get("doc_id"))
    settings = load_settings()
    vector_store = VectorStoreFactory.create(
        VectorStoreSettings(
            provider=settings.vector_store.provider,
            persist_directory=settings.vector_store.persist_directory,
            collection_name=(str(arguments.get("collection", "")).strip() or settings.vector_store.collection_name),
        )
    )

    # Reuse get_by_ids path first (when caller passes chunk id directly as doc_id).
    records = vector_store.get_by_ids([doc_id])
    if not records:
        raise ValueError(f"doc_id not found: {doc_id}")

    metadata = dict(records[0].get("metadata") or {})
    title = (
        str(metadata.get("title") or "").strip()
        or str(metadata.get("source_path") or metadata.get("source") or doc_id).split("/")[-1]
    )
    summary = str(metadata.get("summary") or records[0].get("text") or "").strip()
    if len(summary) > 240:
        summary = summary[:240] + "..."
    tags_raw = metadata.get("tags")
    tags: List[str]
    if isinstance(tags_raw, list):
        tags = [str(item) for item in tags_raw]
    elif tags_raw:
        tags = [str(tags_raw)]
    else:
        tags = []

    payload = {"doc_id": doc_id, "title": title, "summary": summary, "tags": tags}
    return {
        "content": [{"type": "text", "text": f"{title}\n\n{summary}"}],
        "structuredContent": payload,
    }
