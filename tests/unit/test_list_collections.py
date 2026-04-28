"""Unit tests for list_collections MCP tool (E4)."""

from __future__ import annotations

import pytest

from mcp_server.tools.list_collections import list_collections


@pytest.mark.unit
def test_list_collections_returns_directory_names(tmp_path):
    (tmp_path / "collection_a").mkdir()
    (tmp_path / "collection_b").mkdir()
    (tmp_path / "collection_a" / "doc1.md").write_text("hello", encoding="utf-8")
    (tmp_path / "collection_b" / "doc2.md").write_text("world", encoding="utf-8")

    out = list_collections({"_documents_root": str(tmp_path)})
    collections = out["structuredContent"]["collections"]
    names = [item["name"] for item in collections]

    assert names == ["collection_a", "collection_b"]
    assert "可用集合" in out["content"][0]["text"]
