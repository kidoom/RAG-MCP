"""Unit tests for BatchProcessor (C10)."""

from __future__ import annotations

from dataclasses import replace
from typing import List

import pytest
import yaml

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord
from ingestion.embedding import BatchProcessor

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
    return Settings.from_dict(yaml.safe_load(_MINIMAL_SETTINGS_YAML.format(batch_size=batch_size)))


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


class _FakeDenseEncoder:
    def __init__(self):
        self.calls: List[List[str]] = []

    def encode(self, chunks: List[Chunk], trace=None) -> List[ChunkRecord]:
        self.calls.append([c.id for c in chunks])
        return [
            ChunkRecord(
                id=c.id,
                text=c.text,
                metadata=dict(c.metadata),
                dense_vector=[0.1, 0.2, 0.3],
                sparse_vector=None,
            )
            for c in chunks
        ]


class _FakeSparseEncoder:
    def __init__(self):
        self.calls: List[List[str]] = []

    def encode(self, chunks: List[Chunk], trace=None) -> List[ChunkRecord]:
        self.calls.append([c.id for c in chunks])
        return [
            ChunkRecord(
                id=c.id,
                text=c.text,
                metadata=dict(c.metadata),
                dense_vector=None,
                sparse_vector={
                    "terms": {"text": 1},
                    "term_weights": {"text": 1.0},
                    "doc_length": 1,
                    "unique_terms": 1,
                },
            )
            for c in chunks
        ]


def test_batch_processor_splits_into_three_batches_for_five_chunks() -> None:
    dense = _FakeDenseEncoder()
    sparse = _FakeSparseEncoder()
    p = BatchProcessor(_settings(batch_size=2), dense_encoder=dense, sparse_encoder=sparse)
    out = p.process(_chunks(5))
    assert len(out) == 5
    assert [r.id for r in out] == ["c0", "c1", "c2", "c3", "c4"]
    assert dense.calls == [["c0", "c1"], ["c2", "c3"], ["c4"]]
    assert sparse.calls == [["c0", "c1"], ["c2", "c3"], ["c4"]]


def test_batch_processor_merges_dense_and_sparse_fields() -> None:
    p = BatchProcessor(
        _settings(batch_size=2), dense_encoder=_FakeDenseEncoder(), sparse_encoder=_FakeSparseEncoder()
    )
    rec = p.process(_chunks(1))[0]
    assert rec.dense_vector == [0.1, 0.2, 0.3]
    assert rec.sparse_vector is not None
    assert rec.sparse_vector["doc_length"] == 1


def test_batch_processor_empty_input_returns_empty() -> None:
    p = BatchProcessor(
        _settings(batch_size=2), dense_encoder=_FakeDenseEncoder(), sparse_encoder=_FakeSparseEncoder()
    )
    assert p.process([]) == []


def test_batch_processor_raises_on_count_mismatch() -> None:
    class BadSparse(_FakeSparseEncoder):
        def encode(self, chunks: List[Chunk], trace=None) -> List[ChunkRecord]:  # type: ignore[override]
            out = super().encode(chunks, trace=trace)
            return out[:-1]

    p = BatchProcessor(
        _settings(batch_size=2), dense_encoder=_FakeDenseEncoder(), sparse_encoder=BadSparse()
    )
    with pytest.raises(ValueError, match="count mismatch"):
        p.process(_chunks(2))


def test_batch_processor_raises_on_id_mismatch() -> None:
    class BadSparse(_FakeSparseEncoder):
        def encode(self, chunks: List[Chunk], trace=None) -> List[ChunkRecord]:  # type: ignore[override]
            out = super().encode(chunks, trace=trace)
            out[0].id = "other-id"
            return out

    p = BatchProcessor(
        _settings(batch_size=2), dense_encoder=_FakeDenseEncoder(), sparse_encoder=BadSparse()
    )
    with pytest.raises(ValueError, match="id mismatch"):
        p.process(_chunks(2))


def test_batch_processor_records_trace_with_elapsed_ms() -> None:
    ticks = iter([100.0, 100.01, 100.02, 100.03, 100.04, 100.05])
    p = BatchProcessor(
        _settings(batch_size=2),
        dense_encoder=_FakeDenseEncoder(),
        sparse_encoder=_FakeSparseEncoder(),
        time_fn=lambda: next(ticks),
    )
    tr = TraceContext(trace_type="ingestion")
    p.process(_chunks(5), trace=tr)
    stages = tr.stages
    assert any(s.get("stage") == "batch_processor" for s in stages)
    batch_stages = [s for s in stages if s.get("stage") == "batch_processor_batch"]
    assert len(batch_stages) == 3
    assert all("elapsed_ms" in s for s in batch_stages)


def test_batch_processor_requires_ingestion_settings() -> None:
    s = _settings()
    broken = replace(s, ingestion=None)
    with pytest.raises(ValueError, match="ingestion"):
        BatchProcessor(broken)  # type: ignore[arg-type]
