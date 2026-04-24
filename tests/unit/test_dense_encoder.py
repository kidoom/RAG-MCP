"""Unit tests for DenseEncoder (C8)."""

from __future__ import annotations

from dataclasses import replace
from typing import List

import pytest
import yaml

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.embedding import DenseEncoder
from libs.embedding import BaseEmbedding, EmbeddingSettings

_MINIMAL_SETTINGS_YAML = """
llm:
  provider: openai
  model: gpt-4o
  temperature: 0.0
  max_tokens: 1024
  api_key: test-key
embedding:
  provider: openai
  model: text-embedding-3-small
  dimensions: 3
  api_key: test-key
vector_store:
  provider: chroma
  persist_directory: ./data/db/chroma
retrieval:
  dense_top_k: 20
  sparse_top_k: 20
  fusion_top_k: 10
  rrf_k: 60
rerank:
  enabled: false
  provider: none
evaluation:
  enabled: false
  provider: custom
  metrics: [hit_rate]
observability:
  log_level: INFO
  trace_enabled: false
  trace_file: ./logs/traces.jsonl
  structured_logging: false
vision_llm:
  enabled: false
  provider: openai
  model: gpt-4o
ingestion:
  chunk_size: 100
  chunk_overlap: 0
  splitter: recursive
  batch_size: {batch_size}
"""


def _settings(batch_size: int = 2) -> Settings:
    raw = yaml.safe_load(_MINIMAL_SETTINGS_YAML.format(batch_size=batch_size))
    return Settings.from_dict(raw)


def _chunks(n: int) -> List[Chunk]:
    return [
        Chunk(
            id=f"c{i}",
            text=f"text {i}",
            metadata={"source_path": "/docs/x.pdf", "chunk_index": i},
            start_offset=i * 10,
            end_offset=i * 10 + 5,
            source_ref="doc1",
        )
        for i in range(n)
    ]


class _FakeEmbedding(BaseEmbedding):
    def __init__(self, vectors_by_batch: List[List[List[float]]] | None = None):
        super().__init__(EmbeddingSettings(provider="openai", model="m", dimensions=3))
        self.vectors_by_batch = vectors_by_batch or []
        self.calls: List[List[str]] = []

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        self.calls.append(list(texts))
        if self.vectors_by_batch:
            return self.vectors_by_batch.pop(0)
        return [[0.1, 0.2, 0.3] for _ in texts]

    def embed_query(self, query: str) -> List[float]:
        return [0.1, 0.2, 0.3]


def test_dense_encoder_returns_chunk_records_with_vectors() -> None:
    encoder = DenseEncoder(_settings(batch_size=10), embedding_client=_FakeEmbedding())
    out = encoder.encode(_chunks(3))

    assert len(out) == 3
    assert [r.id for r in out] == ["c0", "c1", "c2"]
    assert all(r.dense_vector == [0.1, 0.2, 0.3] for r in out)
    assert all(r.sparse_vector is None for r in out)


def test_dense_encoder_batches_calls_and_preserves_order() -> None:
    fake = _FakeEmbedding()
    encoder = DenseEncoder(_settings(batch_size=2), embedding_client=fake)
    out = encoder.encode(_chunks(5))

    assert len(out) == 5
    assert fake.calls == [
        ["text 0", "text 1"],
        ["text 2", "text 3"],
        ["text 4"],
    ]
    assert [r.id for r in out] == ["c0", "c1", "c2", "c3", "c4"]


def test_dense_encoder_empty_input_returns_empty() -> None:
    encoder = DenseEncoder(_settings(), embedding_client=_FakeEmbedding())
    assert encoder.encode([]) == []


def test_dense_encoder_raises_on_vector_count_mismatch() -> None:
    fake = _FakeEmbedding(vectors_by_batch=[[[0.1, 0.2, 0.3]]])
    encoder = DenseEncoder(_settings(batch_size=2), embedding_client=fake)
    with pytest.raises(ValueError, match="output size mismatch"):
        encoder.encode(_chunks(2))


def test_dense_encoder_raises_on_dimension_mismatch() -> None:
    fake = _FakeEmbedding(vectors_by_batch=[[[0.1, 0.2], [0.3, 0.4]]])
    encoder = DenseEncoder(_settings(batch_size=2), embedding_client=fake)
    with pytest.raises(ValueError, match="dimension mismatch"):
        encoder.encode(_chunks(2))


def test_dense_encoder_records_trace() -> None:
    encoder = DenseEncoder(_settings(batch_size=2), embedding_client=_FakeEmbedding())
    trace = TraceContext(trace_type="ingestion")
    encoder.encode(_chunks(3), trace=trace)
    stages = [s.get("stage") for s in trace.stages]
    assert "dense_encoder" in stages
    assert stages.count("dense_encoder_batch") == 2


def test_dense_encoder_requires_ingestion_settings() -> None:
    s = _settings()
    broken = replace(s, ingestion=None)
    with pytest.raises(ValueError, match="ingestion"):
        DenseEncoder(broken)  # type: ignore[arg-type]
