"""Unit tests for list_collections MCP tool (E4)."""

from __future__ import annotations

import importlib

import pytest

tool_module = importlib.import_module("mcp_server.tools.list_collections")


@pytest.mark.unit
def test_list_collections_returns_directory_names(monkeypatch):
    class _FakeSettings:
        class vector_store:
            provider = "chroma"
            persist_directory = "unused"
            collection_name = "default"

    class _FakeStore:
        def get_all_collections(self):
            return ["collection_a", "collection_b"]

    monkeypatch.setattr(tool_module, "load_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        tool_module.VectorStoreFactory,
        "create",
        lambda _settings: _FakeStore(),
    )

    out = tool_module.list_collections({})
    collections = out["structuredContent"]["collections"]
    names = list(collections)

    assert names == ["collection_a", "collection_b"]
    assert "可用集合" in out["content"][0]["text"]
