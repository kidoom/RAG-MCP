"""Unit tests for SparseEncoder (C9)."""

from __future__ import annotations

from dataclasses import replace
from typing import List

import pytest
import yaml

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.embedding import SparseEncoder

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
  batch_size: 10
"""


def _settings() -> Settings:
    return Settings.from_dict(yaml.safe_load(_MINIMAL_SETTINGS_YAML))


def _chunks() -> List[Chunk]:
    return [
        Chunk(
            id="c0",
            text="The system uses BM25 and BM25 for sparse retrieval.",
            metadata={"source_path": "/docs/a.pdf", "chunk_index": 0},
            start_offset=0,
            end_offset=20,
            source_ref="doc1",
        ),
        Chunk(
            id="c1",
            text="",
            metadata={"source_path": "/docs/a.pdf", "chunk_index": 1},
            start_offset=20,
            end_offset=20,
            source_ref="doc1",
        ),
    ]


def test_sparse_encoder_outputs_chunk_records() -> None:
    encoder = SparseEncoder(_settings())
    out = encoder.encode(_chunks())
    assert len(out) == 2
    assert out[0].id == "c0"
    assert out[0].text.startswith("The system uses")
    assert out[0].dense_vector is None
    assert isinstance(out[0].sparse_vector, dict)


def test_sparse_encoder_produces_term_stats() -> None:
    encoder = SparseEncoder(_settings())
    rec = encoder.encode([_chunks()[0]])[0]
    sv = rec.sparse_vector or {}
    assert sv["doc_length"] > 0
    assert sv["unique_terms"] > 0
    assert "terms" in sv and "term_weights" in sv
    assert sv["terms"]["bm25"] == 2
    assert "the" not in sv["terms"]  # stopword removed


def test_sparse_encoder_handles_empty_text_explicitly() -> None:
    encoder = SparseEncoder(_settings())
    rec = encoder.encode([_chunks()[1]])[0]
    assert rec.sparse_vector == {
        "terms": {},
        "term_weights": {},
        "doc_length": 0,
        "unique_terms": 0,
    }


def test_sparse_encoder_preserves_metadata() -> None:
    encoder = SparseEncoder(_settings())
    rec = encoder.encode([_chunks()[0]])[0]
    assert rec.metadata["source_path"] == "/docs/a.pdf"
    assert rec.metadata["chunk_index"] == 0


def test_sparse_encoder_records_trace() -> None:
    encoder = SparseEncoder(_settings())
    tr = TraceContext(trace_type="ingestion")
    encoder.encode(_chunks(), trace=tr)
    assert any(s.get("stage") == "sparse_encoder" for s in tr.stages)


def test_sparse_encoder_requires_ingestion_settings() -> None:
    s = _settings()
    broken = replace(s, ingestion=None)
    with pytest.raises(ValueError, match="ingestion"):
        SparseEncoder(broken)  # type: ignore[arg-type]
