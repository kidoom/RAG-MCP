"""Unit tests for MCP response builder (E3)."""

from __future__ import annotations

import pytest

from core.response import ResponseBuilder
from core.types import RetrievalResult


@pytest.mark.unit
def test_response_builder_builds_markdown_with_citations():
    builder = ResponseBuilder()
    results = [
        RetrievalResult(
            chunk_id="chunk-1",
            score=0.91,
            text="Azure 配置需要设置 endpoint 和 api key。",
            metadata={"source_path": "docs/azure.md", "page": 2},
        )
    ]

    out = builder.build(retrieval_results=results, query="如何配置 Azure")
    assert out["content"][0]["type"] == "text"
    assert "[1]" in out["content"][0]["text"]
    assert out["structuredContent"]["citations"][0]["chunk_id"] == "chunk-1"
    assert out["structuredContent"]["citations"][0]["source"] == "docs/azure.md"


@pytest.mark.unit
def test_response_builder_returns_friendly_message_for_empty_results():
    builder = ResponseBuilder()
    out = builder.build(retrieval_results=[], query="空查询结果测试")

    assert "未找到相关文档" in out["content"][0]["text"]
    assert out["structuredContent"]["citations"] == []
