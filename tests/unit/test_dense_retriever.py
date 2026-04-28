"""Unit tests for DenseRetriever (D2)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from core.query_engine.dense_retriever import DenseRetriever
from core.types import RetrievalResult
from libs.vector_store import QueryResult


class FakeEmbeddingClient:
    def __init__(self, vector: List[float]):
        self.vector = vector
        self.calls: List[str] = []

    def embed_query(self, query: str) -> List[float]:
        self.calls.append(query)
        return self.vector


class FakeVectorStore:
    def __init__(self, results: List[QueryResult]):
        self.results = results
        self.calls: List[Dict[str, Any]] = []

    def query(
        self,
        vector: List[float],
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        trace: Any = None,
    ) -> List[QueryResult]:
        self.calls.append(
            {"vector": vector, "top_k": top_k, "filters": filters, "trace": trace}
        )
        return self.results


@dataclass
class _MinimalSettings:
    embedding: Any
    vector_store: Any


def _make_settings() -> _MinimalSettings:
    embedding = type(
        "EmbeddingCfg",
        (),
        {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "dimensions": 3,
            "api_key": "",
            "base_url": "",
            "azure_endpoint": "",
            "deployment_name": "",
            "api_version": "",
        },
    )()
    vector_store = type(
        "VectorStoreCfg",
        (),
        {
            "provider": "chroma",
            "persist_directory": "./data/db/chroma",
            "collection_name": "test",
        },
    )()
    return _MinimalSettings(embedding=embedding, vector_store=vector_store)


def test_dense_retriever_orchestrates_embedding_and_query_calls() -> None:
    embedding = FakeEmbeddingClient(vector=[0.1, 0.2, 0.3])
    store = FakeVectorStore(
        results=[
            QueryResult(
                id="chunk_001",
                score=0.91,
                text="Azure OpenAI setup notes",
                metadata={"collection": "docs"},
            )
        ]
    )
    retriever = DenseRetriever(
        settings=_make_settings(), embedding_client=embedding, vector_store=store
    )

    results = retriever.retrieve(
        query="How to configure Azure OpenAI?",
        top_k=3,
        filters={"collection": "docs"},
    )

    assert embedding.calls == ["How to configure Azure OpenAI?"]
    assert store.calls == [
        {
            "vector": [0.1, 0.2, 0.3],
            "top_k": 3,
            "filters": {"collection": "docs"},
            "trace": None,
        }
    ]
    assert results == [
        RetrievalResult(
            chunk_id="chunk_001",
            score=0.91,
            text="Azure OpenAI setup notes",
            metadata={"collection": "docs"},
        )
    ]


def test_dense_retriever_normalizes_empty_text_and_metadata() -> None:
    embedding = FakeEmbeddingClient(vector=[1.0, 0.0])
    store = FakeVectorStore(results=[QueryResult(id="c1", score=0.4, text="", metadata={})])
    retriever = DenseRetriever(
        settings=_make_settings(), embedding_client=embedding, vector_store=store
    )

    results = retriever.retrieve(query="test", top_k=1)

    assert results[0].text == ""
    assert results[0].metadata == {}


def test_dense_retriever_validates_input() -> None:
    retriever = DenseRetriever(
        settings=_make_settings(),
        embedding_client=FakeEmbeddingClient(vector=[0.2, 0.1]),
        vector_store=FakeVectorStore(results=[]),
    )

    with pytest.raises(ValueError, match="non-empty string"):
        retriever.retrieve(query="  ", top_k=1)
    with pytest.raises(ValueError, match="top_k must be positive"):
        retriever.retrieve(query="ok", top_k=0)
