"""Unit tests for Pipeline progress callback (F5)."""

from __future__ import annotations

from typing import List

import yaml

from core.settings import Settings
from ingestion.pipeline import IngestionPipeline, ProgressCallback


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


def test_progress_callback_type_hint() -> None:
    """Verify ProgressCallback type alias is importable and callable compatible."""
    calls: list = []

    def handler(stage: str, current: int, total: int) -> None:
        calls.append((stage, current, total))

    cb: ProgressCallback = handler
    cb("test", 1, 10)
    assert calls == [("test", 1, 10)]


def test_pipeline_constructor_does_not_require_on_progress() -> None:
    """Verify pipeline accepts no on_progress parameter at init time."""
    settings = Settings.from_dict(yaml.safe_load(_MINIMAL_SETTINGS_YAML))
    pipeline = IngestionPipeline(settings)
    assert pipeline is not None


def test_fire_helper_with_none_callback_does_not_raise() -> None:
    from ingestion.pipeline import _fire
    _fire(None, "stage", 0, 1)  # must not raise


def test_fire_helper_calls_callback() -> None:
    called: List[tuple] = []

    def cb(stage: str, current: int, total: int) -> None:
        called.append((stage, current, total))

    from ingestion.pipeline import _fire
    _fire(cb, "split", 3, 10)
    assert called == [("split", 3, 10)]


def test_estimate_chunk_count() -> None:
    from ingestion.pipeline import _estimate_chunk_count
    from core.types import Document

    doc = Document(id="d1", text="a" * 1000, metadata={})
    n = _estimate_chunk_count(doc)
    assert n >= 1
