"""Unit tests for QueryProcessor (D1)."""

from __future__ import annotations

import pytest

from core.query_engine import QueryProcessor


def test_process_extracts_keywords_and_normalizes_query() -> None:
    processor = QueryProcessor()
    result = processor.process("  How to configure   Azure OpenAI for RAG?  ")

    assert result.normalized_query == "How to configure Azure OpenAI for RAG?"
    assert "azure" in result.keywords
    assert "openai" in result.keywords
    assert "rag" in result.keywords
    assert "how" not in result.keywords


def test_process_returns_empty_filters_when_not_provided() -> None:
    processor = QueryProcessor()
    result = processor.process("azure setup")
    assert result.filters == {}


def test_process_normalizes_filter_values() -> None:
    processor = QueryProcessor()
    result = processor.process(
        "azure setup",
        filters={
            "collection": " docs ",
            "doc_type": "  ",
            "tags": ["azure", "", None, "rag"],
            "empty": None,
        },
    )
    assert result.filters == {"collection": "docs", "tags": ["azure", "rag"]}


def test_process_deduplicates_keywords_with_stable_order() -> None:
    processor = QueryProcessor()
    result = processor.process("Azure azure OpenAI openai Azure")
    assert result.keywords == ["azure", "openai"]


def test_process_supports_cjk_tokens() -> None:
    processor = QueryProcessor()
    result = processor.process("如何 配置 Azure OpenAI 服务")
    assert "如何" in result.keywords
    assert "配置" in result.keywords
    assert "azure" in result.keywords


def test_process_raises_for_empty_query() -> None:
    processor = QueryProcessor()
    with pytest.raises(ValueError, match="must not be empty"):
        processor.process("   ")


def test_process_raises_for_invalid_filters_type() -> None:
    processor = QueryProcessor()
    with pytest.raises(TypeError, match="filters must be a mapping"):
        processor.process("azure", filters=["not", "dict"])  # type: ignore[arg-type]
