"""Unit tests for get_document_summary MCP tool (E5)."""

from __future__ import annotations

from dataclasses import dataclass
import importlib

import pytest

tool_module = importlib.import_module("mcp_server.tools.get_document_summary")


@dataclass
class _FakeVectorStore:
    records: list[dict]

    def get_by_ids(self, _ids):
        return self.records


@pytest.mark.unit
def test_get_document_summary_returns_structured_payload(monkeypatch):
    class _FakeSettings:
        class vector_store:
            provider = "chroma"
            persist_directory = "unused"
            collection_name = "default"

    monkeypatch.setattr(tool_module, "load_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        tool_module.VectorStoreFactory,
        "create",
        lambda _settings: _FakeVectorStore(
            [
                {
                    "id": "doc-1",
                    "text": "This is a test summary body.",
                    "metadata": {"title": "Doc Title", "tags": ["a", "b"]},
                }
            ]
        ),
    )

    out = tool_module.get_document_summary({"doc_id": "doc-1"})
    assert out["structuredContent"]["doc_id"] == "doc-1"
    assert out["structuredContent"]["title"] == "Doc Title"
    assert out["structuredContent"]["tags"] == ["a", "b"]


@pytest.mark.unit
def test_get_document_summary_not_found_raises_value_error(monkeypatch):
    class _FakeSettings:
        class vector_store:
            provider = "chroma"
            persist_directory = "unused"
            collection_name = "default"

    monkeypatch.setattr(tool_module, "load_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        tool_module.VectorStoreFactory,
        "create",
        lambda _settings: _FakeVectorStore([]),
    )

    with pytest.raises(ValueError, match="doc_id not found"):
        tool_module.get_document_summary({"doc_id": "missing"})
