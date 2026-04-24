"""Unit tests for ChunkRefiner and TraceContext (C5)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.base_transform import BaseTransform
from ingestion.transform.chunk_refiner import ChunkRefiner
from libs.llm.base_llm import BaseLLM, LLMSettings as LibLLMSettings


FIXTURES_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "noisy_chunks.json"

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


class _FakeLLM(BaseLLM):
    def __init__(self, out: str = "LLM_REFINED", exc: Exception | None = None):
        super().__init__(LibLLMSettings(provider="openai", model="gpt-4o", api_key="k"))
        self._out = out
        self._exc = exc

    def generate(self, prompt: str, **kwargs) -> str:
        if self._exc:
            raise self._exc
        return self._out

    def chat(self, messages, **kwargs) -> str:
        return "ok"


# ---------------------------------------------------------------------------
# TraceContext
# ---------------------------------------------------------------------------


def test_trace_context_record_stage():
    t = TraceContext(trace_type="ingestion")
    t.record_stage("load", items=3)
    assert len(t.stages) == 1
    assert t.stages[0]["stage"] == "load"
    assert t.stages[0]["items"] == 3


def test_trace_context_to_dict_has_trace_id_and_type():
    t = TraceContext(trace_type="query")
    d = t.to_dict()
    assert d["trace_type"] == "query"
    assert "trace_id" in d and len(d["trace_id"]) > 8
    assert d["stages"] == []


# ---------------------------------------------------------------------------
# BaseTransform
# ---------------------------------------------------------------------------


def test_base_transform_is_abstract():
    with pytest.raises(TypeError):
        BaseTransform()  # type: ignore[abstract,misc]


# ---------------------------------------------------------------------------
# Rule-based refinement (fixtures)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def noisy_fixtures() -> dict:
    return json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))


def test_rule_typical_noise_trims_blank_runs(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine(noisy_fixtures["typical_noise_scenario"]["text"])
    assert "Real paragraph one" in out
    assert "\n\n\n\n" not in out


def test_rule_ocr_style_spaces_collapsed(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine(noisy_fixtures["ocr_errors"]["text"])
    assert "  " not in out
    assert "The quick brown fox jumps" in out


def test_rule_page_x_of_y_removed(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine(noisy_fixtures["page_header_footer"]["text"])
    assert "Page 2 of 10" not in out
    assert "Body continues" in out


def test_rule_excessive_whitespace_normalized(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine(noisy_fixtures["excessive_whitespace"]["text"])
    assert "\n\n\n" not in out


def test_rule_html_comment_stripped(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine(noisy_fixtures["format_markers"]["text"])
    assert "<!--" not in out
    assert "Visible" in out and "content" in out


def test_rule_clean_text_not_erased(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    raw = noisy_fixtures["clean_text"]["text"]
    out = r._rule_based_refine(raw)
    assert "Single paragraph" in out


def test_rule_code_fence_inner_preserved(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine(noisy_fixtures["code_blocks"]["text"])
    assert "```python" in out
    assert "    return 42" in out


def test_rule_mixed_noise(noisy_fixtures):
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine(noisy_fixtures["mixed_noise"]["text"])
    assert "<!--" not in out
    assert "Page 1 of 2" not in out


def test_rule_preserves_markdown_heading():
    r = ChunkRefiner(_settings(False), llm=None)
    text = "## Section\n\nBody here."
    out = r._rule_based_refine(text)
    assert "## Section" in out


# ---------------------------------------------------------------------------
# Transform pipeline
# ---------------------------------------------------------------------------


def test_transform_refined_by_rule_without_llm():
    r = ChunkRefiner(_settings(False), llm=None)
    chunks = [_chunk("a   b")]
    out = r.transform(chunks)
    assert len(out) == 1
    assert out[0].metadata["refined_by"] == "rule"
    assert "refinement_fallback_reason" not in out[0].metadata


def test_transform_mock_llm_sets_refined_by_llm():
    r = ChunkRefiner(_settings(True), llm=_FakeLLM("polished text"))
    out = r.transform([_chunk("  noisy  ")])
    assert out[0].text == "polished text"
    assert out[0].metadata["refined_by"] == "llm"


def test_transform_llm_exception_falls_back_to_rule():
    r = ChunkRefiner(_settings(True), llm=_FakeLLM(exc=RuntimeError("api down")))
    out = r.transform([_chunk("hello   world")])
    assert out[0].metadata["refined_by"] == "rule"
    assert out[0].metadata.get("refinement_fallback_reason") == "llm_failed_or_empty"


def test_transform_llm_empty_string_falls_back():
    class EmptyLLM(_FakeLLM):
        def generate(self, prompt: str, **kwargs) -> str:  # type: ignore[override]
            return "   "

    r = ChunkRefiner(_settings(True), llm=EmptyLLM())
    out = r.transform([_chunk("aa   bb")])
    assert out[0].metadata["refined_by"] == "rule"
    assert out[0].metadata.get("refinement_fallback_reason") == "llm_failed_or_empty"


def test_transform_empty_chunk_text():
    r = ChunkRefiner(_settings(False), llm=None)
    out = r.transform([_chunk("   ")])
    assert out[0].text == "   "
    assert out[0].metadata.get("refined_by") == "rule"


def test_transform_per_chunk_error_isolated():
    r = ChunkRefiner(_settings(False), llm=None)
    r._rule_based_refine = MagicMock(side_effect=[ValueError("bad"), "ok"])  # type: ignore[method-assign]

    out = r.transform([_chunk("first", "c0"), _chunk("second", "c1")])
    assert out[0].metadata.get("chunk_refinement_error")
    assert out[0].text == "first"
    assert out[1].text == "ok"
    assert "chunk_refinement_error" not in out[1].metadata


def test_transform_records_trace_stage():
    r = ChunkRefiner(_settings(False), llm=None)
    tr = TraceContext()
    r.transform([_chunk("x")], trace=tr)
    assert tr.stages and tr.stages[0]["stage"] == "chunk_refiner"


def test_transform_preserves_order_and_count():
    r = ChunkRefiner(_settings(False), llm=None)
    chunks = [_chunk("a", "1"), _chunk("b", "2")]
    out = r.transform(chunks)
    assert [c.id for c in out] == ["1", "2"]


def test_settings_ingestion_chunk_refiner_flag():
    s = _settings(True)
    assert s.ingestion is not None
    assert s.ingestion.chunk_refiner is not None
    assert s.ingestion.chunk_refiner.use_llm is True
    s2 = _settings(False)
    assert s2.ingestion is not None
    assert s2.ingestion.chunk_refiner is not None
    assert s2.ingestion.chunk_refiner.use_llm is False


def test_prompt_builtin_when_file_missing(tmp_path):
    missing = tmp_path / "nope.txt"
    r = ChunkRefiner(_settings(False), llm=None, prompt_path=str(missing))
    assert "{text}" in r._prompt_template


def test_llm_success_records_trace_stage():
    r = ChunkRefiner(_settings(True), llm=_FakeLLM("out"))
    tr = TraceContext()
    r.transform([_chunk("in")], trace=tr)
    stages = [s["stage"] for s in tr.stages]
    assert "chunk_refiner_llm_ok" in stages


def test_llm_error_records_trace_stage():
    r = ChunkRefiner(_settings(True), llm=_FakeLLM(exc=ValueError("x")))
    tr = TraceContext()
    r.transform([_chunk("in")], trace=tr)
    assert any(s.get("stage") == "chunk_refiner_llm_error" for s in tr.stages)


def test_rule_does_not_strip_image_placeholder():
    r = ChunkRefiner(_settings(False), llm=None)
    text = "See [IMAGE: img_1] here."
    out = r._rule_based_refine(text)
    assert "[IMAGE: img_1]" in out


def test_chunk_refiner_requires_ingestion_settings():
    class S:
        ingestion = None

    with pytest.raises(ValueError, match="ingestion"):
        ChunkRefiner(S())  # type: ignore[arg-type]


def test_transform_keeps_source_path_in_metadata():
    r = ChunkRefiner(_settings(True), llm=_FakeLLM("z"))
    ch = _chunk("a b")
    out = r.transform([ch])
    assert out[0].metadata["source_path"] == "/docs/x.pdf"


def test_rule_horizontal_rule_line_removed():
    r = ChunkRefiner(_settings(False), llm=None)
    out = r._rule_based_refine("Before\n\n---\n\nAfter")
    assert out == "Before\n\nAfter" or "---" not in out


def test_init_with_explicit_prompt_path_reads_file(tmp_path):
    p = tmp_path / "p.txt"
    p.write_text("Say hi.\n\n{text}", encoding="utf-8")
    r = ChunkRefiner(_settings(False), llm=None, prompt_path=str(p))
    assert "Say hi." in r._prompt_template
