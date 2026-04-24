"""Unit tests for ImageCaptioner fallback behavior (C7)."""

from __future__ import annotations

from dataclasses import replace

import yaml

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.image_captioner import ImageCaptioner
from libs.llm.base_vision_llm import BaseVisionLLM, VisionLLMSettings

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
  enabled: {vision_enabled}
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
    use_llm: false
  image_captioner:
    use_vision_llm: {use_vision_llm}
"""


def _settings(*, use_vision_llm: bool, vision_enabled: bool = True) -> Settings:
    raw = yaml.safe_load(
        _MINIMAL_SETTINGS_YAML.format(
            use_vision_llm=str(use_vision_llm).lower(),
            vision_enabled=str(vision_enabled).lower(),
        )
    )
    return Settings.from_dict(raw)


def _chunk_with_image(cid: str = "c1") -> Chunk:
    return Chunk(
        id=cid,
        text="See figure [IMAGE: img_1] for architecture.",
        metadata={
            "source_path": "/docs/spec.pdf",
            "image_refs": ["img_1"],
            "images": [{"id": "img_1", "path": "/tmp/img_1.png"}],
        },
        start_offset=0,
        end_offset=40,
        source_ref="doc1",
    )


class _FakeVisionLLM(BaseVisionLLM):
    def __init__(self, caption: str = "architecture diagram", fail: bool = False):
        super().__init__(VisionLLMSettings(provider="openai", model="gpt-4o", api_key="k"))
        self._caption = caption
        self._fail = fail
        self.calls = 0

    def chat_with_image(self, text: str, image_path=None, **kwargs) -> str:  # type: ignore[override]
        return self.describe_image(str(image_path), prompt=text)

    def describe_image(self, image_path: str, prompt: str = None) -> str:  # type: ignore[override]
        self.calls += 1
        if self._fail:
            raise RuntimeError("vision api down")
        return self._caption


def test_captioner_uses_vision_llm_when_enabled() -> None:
    s = _settings(use_vision_llm=True, vision_enabled=True)
    fake = _FakeVisionLLM(caption="A system architecture figure.")
    cap = ImageCaptioner(s, vision_llm=fake)

    out = cap.transform([_chunk_with_image()])[0]

    assert fake.calls == 1
    assert out.metadata["image_captions"]["img_1"] == "A system architecture figure."
    assert "has_unprocessed_images" not in out.metadata


def test_captioner_disabled_marks_unprocessed() -> None:
    s = _settings(use_vision_llm=False, vision_enabled=True)
    cap = ImageCaptioner(s, vision_llm=_FakeVisionLLM())

    out = cap.transform([_chunk_with_image()])[0]

    assert "image_captions" not in out.metadata
    assert out.metadata["has_unprocessed_images"] is True
    assert out.metadata["image_refs"] == ["img_1"]


def test_captioner_runtime_failure_falls_back() -> None:
    s = _settings(use_vision_llm=True, vision_enabled=True)
    cap = ImageCaptioner(s, vision_llm=_FakeVisionLLM(fail=True))

    out = cap.transform([_chunk_with_image()])[0]

    assert out.metadata["has_unprocessed_images"] is True
    assert out.metadata.get("unprocessed_image_refs") == ["img_1"]
    assert "image_captions" not in out.metadata


def test_captioner_no_image_refs_noop() -> None:
    s = _settings(use_vision_llm=True, vision_enabled=True)
    cap = ImageCaptioner(s, vision_llm=_FakeVisionLLM())
    chunk = Chunk(
        id="c2",
        text="No images here.",
        metadata={"source_path": "/docs/spec.pdf"},
        start_offset=0,
        end_offset=14,
        source_ref="doc1",
    )
    out = cap.transform([chunk])[0]
    assert out.metadata == chunk.metadata


def test_captioner_records_trace_stages() -> None:
    s = _settings(use_vision_llm=True, vision_enabled=True)
    cap = ImageCaptioner(s, vision_llm=_FakeVisionLLM())
    tr = TraceContext()

    cap.transform([_chunk_with_image()], trace=tr)
    stages = [s.get("stage") for s in tr.stages]

    assert "image_captioner" in stages
    assert "image_captioner_llm_ok" in stages


def test_captioner_requires_ingestion_settings() -> None:
    s = _settings(use_vision_llm=True, vision_enabled=True)
    broken = replace(s, ingestion=None)
    try:
        ImageCaptioner(broken)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "ingestion" in str(exc)
