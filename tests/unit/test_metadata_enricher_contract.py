"""Contract tests for MetadataEnricher (C6)."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
import yaml

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.metadata_enricher import MetadataEnricher
from libs.llm.base_llm import BaseLLM, LLMSettings as LibLLMSettings

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
  dimensions: 1536
  api_key: ""
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
  chunk_refiner:
    use_llm: false
  metadata_enricher:
    use_llm: {use_llm}
"""


def _settings(use_llm: bool) -> Settings:
    raw = yaml.safe_load(_MINIMAL_SETTINGS_YAML.format(use_llm=str(use_llm).lower()))
    return Settings.from_dict(raw)


def _chunk(text: str, cid: str = "c1") -> Chunk:
    return Chunk(
        id=cid,
        text=text,
        metadata={"source_path": "/docs/x.pdf"},
        start_offset=0,
        end_offset=max(1, len(text)),
        source_ref="doc1",
    )


def _assert_nonempty_triple(md: dict) -> None:
    assert isinstance(md.get("title"), str) and md["title"].strip()
    assert isinstance(md.get("summary"), str) and md["summary"].strip()
    assert isinstance(md.get("tags"), list) and len(md["tags"]) >= 1
    assert all(isinstance(t, str) and t.strip() for t in md["tags"])


def test_rule_mode_fills_title_summary_tags() -> None:
    s = _settings(use_llm=False)
    en = MetadataEnricher(s)
    out = en.transform(
        [
            _chunk(
                "Introduction\n\n"
                "This module implements hybrid retrieval with dense and sparse paths."
            )
        ]
    )[0]
    _assert_nonempty_triple(out.metadata)
    assert out.metadata["enriched_by"] == "rule"
    assert "hybrid" in " ".join(out.metadata["tags"]).lower() or "retrieval" in " ".join(
        out.metadata["tags"]
    ).lower() or "module" in " ".join(out.metadata["tags"]).lower()


def test_empty_chunk_still_non_empty_fields() -> None:
    s = _settings(use_llm=False)
    en = MetadataEnricher(s)
    out = en.transform([_chunk("   \n\t  ")])[0]
    _assert_nonempty_triple(out.metadata)
    assert "empty" in " ".join(out.metadata["tags"]).lower() or out.metadata["title"]


def test_llm_mode_uses_response_when_valid() -> None:
    s = _settings(use_llm=True)
    mock_llm = MagicMock(spec=BaseLLM)
    mock_llm.settings = LibLLMSettings(provider="openai", model="x")
    mock_llm.generate.return_value = (
        '{"title": "T", "summary": "S body.", "tags": ["a", "b", "c"]}'
    )
    en = MetadataEnricher(s, llm=mock_llm)
    out = en.transform([_chunk("any text long enough for chunk")])[0]
    assert out.metadata["enriched_by"] == "llm"
    assert out.metadata["title"] == "T"
    assert out.metadata["summary"] == "S body."
    assert out.metadata["tags"] == ["a", "b", "c"]
    mock_llm.generate.assert_called_once()


def test_llm_mode_falls_back_on_exception() -> None:
    s = _settings(use_llm=True)
    mock_llm = MagicMock(spec=BaseLLM)
    mock_llm.settings = LibLLMSettings(provider="openai", model="x")
    mock_llm.generate.side_effect = RuntimeError("network")

    en = MetadataEnricher(s, llm=mock_llm)
    out = en.transform([_chunk("Valid body text for rule fallback and keywords here.")])[
        0
    ]
    assert out.metadata["enriched_by"] == "rule"
    assert out.metadata.get("metadata_enrichment_fallback_reason") == "llm_failed_or_invalid"
    _assert_nonempty_triple(out.metadata)


def test_llm_mode_falls_back_on_invalid_json() -> None:
    s = _settings(use_llm=True)
    mock_llm = MagicMock(spec=BaseLLM)
    mock_llm.settings = LibLLMSettings(provider="openai", model="x")
    mock_llm.generate.return_value = "not json at all"
    en = MetadataEnricher(s, llm=mock_llm)
    out = en.transform([_chunk("Some content for the chunk.")])[0]
    assert out.metadata["enriched_by"] == "rule"
    assert out.metadata.get("metadata_enrichment_fallback_reason") == "llm_failed_or_invalid"


def test_json_fence_stripped() -> None:
    s = _settings(use_llm=True)
    mock_llm = MagicMock(spec=BaseLLM)
    mock_llm.settings = LibLLMSettings(provider="openai", model="x")
    mock_llm.generate.return_value = (
        '```json\n{"title": "X", "summary": "Y.", "tags": ["t"]}\n```'
    )
    en = MetadataEnricher(s, llm=mock_llm)
    out = en.transform([_chunk("x")])[0]
    assert out.metadata["enriched_by"] == "llm"
    assert out.metadata["title"] == "X"


def test_per_chunk_failure_does_not_stop_batch() -> None:
    s = _settings(use_llm=False)
    en = MetadataEnricher(s)
    good = _chunk("alpha beta gamma delta epsilon zeta", "ok")
    bad = _chunk("x", "bad")

    orig = en._enrich_one

    def flaky(c: Chunk, tr: TraceContext | None) -> Chunk:  # type: ignore[no-untyped-def]
        if c.id == "bad":
            raise ValueError("boom")
        return orig(c, tr)

    en._enrich_one = flaky  # type: ignore[assignment]
    out = en.transform([good, bad])
    assert out[0].metadata["enriched_by"] == "rule"
    assert "metadata_enrichment_error" in out[1].metadata
    _assert_nonempty_triple(out[1].metadata)


def test_trace_records_stage() -> None:
    s = _settings(use_llm=False)
    en = MetadataEnricher(s)
    tr = TraceContext()
    en.transform([_chunk("hi")], trace=tr)
    names = [x.get("stage") for x in tr.stages]
    assert "metadata_enricher" in names


def test_settings_rejects_missing_ingestion() -> None:
    base = _settings(False)
    s = replace(base, ingestion=None)
    with pytest.raises(ValueError, match="ingestion"):
        MetadataEnricher(s)
