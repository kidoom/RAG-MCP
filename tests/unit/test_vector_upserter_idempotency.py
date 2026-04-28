"""Unit tests for VectorUpserter (C12)."""

from __future__ import annotations

from typing import List

import pytest
import yaml

from core.settings import Settings
from core.types import ChunkRecord
from ingestion.storage import VectorUpserter
from libs.vector_store import VectorRecord

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
  collection_name: test
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
  batch_size: 2
"""


def _settings() -> Settings:
    return Settings.from_dict(yaml.safe_load(_MINIMAL_SETTINGS_YAML))


def _chunk_record(text: str, *, chunk_index: int = 0, source_path: str = "/docs/a.pdf") -> ChunkRecord:
    return ChunkRecord(
        id=f"raw-{chunk_index}",
        text=text,
        metadata={"source_path": source_path, "chunk_index": chunk_index},
        dense_vector=[0.1, 0.2, 0.3],
        sparse_vector=None,
    )


class _FakeVectorStore:
    def __init__(self) -> None:
        self.calls: List[List[VectorRecord]] = []

    def upsert(self, records: List[VectorRecord], trace=None) -> None:
        self.calls.append(records)


def test_vector_upserter_same_chunk_generates_same_id() -> None:
    fake = _FakeVectorStore()
    upserter = VectorUpserter(_settings(), vector_store=fake)  # type: ignore[arg-type]
    c1 = _chunk_record("same text", chunk_index=1)
    c2 = _chunk_record("same text", chunk_index=1)
    out1 = upserter.upsert([c1])
    out2 = upserter.upsert([c2])
    assert out1[0].id == out2[0].id


def test_vector_upserter_content_change_changes_id() -> None:
    fake = _FakeVectorStore()
    upserter = VectorUpserter(_settings(), vector_store=fake)  # type: ignore[arg-type]
    a = _chunk_record("text v1", chunk_index=2)
    b = _chunk_record("text v2", chunk_index=2)
    out_a = upserter.upsert([a])
    out_b = upserter.upsert([b])
    assert out_a[0].id != out_b[0].id


def test_vector_upserter_batch_upsert_keeps_order() -> None:
    fake = _FakeVectorStore()
    upserter = VectorUpserter(_settings(), vector_store=fake)  # type: ignore[arg-type]
    records = [
        _chunk_record("a", chunk_index=0),
        _chunk_record("b", chunk_index=1),
        _chunk_record("c", chunk_index=2),
    ]
    out = upserter.upsert(records)
    assert len(fake.calls) == 1
    assert [r.id for r in out] == [r.id for r in fake.calls[0]]
    assert [r.text for r in fake.calls[0]] == ["a", "b", "c"]


def test_vector_upserter_requires_source_path() -> None:
    upserter = VectorUpserter(_settings(), vector_store=_FakeVectorStore())  # type: ignore[arg-type]
    bad = ChunkRecord(
        id="x",
        text="content",
        metadata={"chunk_index": 1},
        dense_vector=[0.1, 0.2, 0.3],
    )
    with pytest.raises(ValueError, match="source_path"):
        upserter.upsert([bad])


def test_vector_upserter_requires_dense_vector() -> None:
    upserter = VectorUpserter(_settings(), vector_store=_FakeVectorStore())  # type: ignore[arg-type]
    bad = ChunkRecord(
        id="x",
        text="content",
        metadata={"source_path": "/docs/a.pdf", "chunk_index": 1},
        dense_vector=None,
    )
    with pytest.raises(ValueError, match="dense_vector"):
        upserter.upsert([bad])
