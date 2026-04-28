"""Integration tests for IngestionPipeline (C14 / F4 / F5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord, Document
from ingestion.pipeline import IngestionPipeline, IngestionPipelineError

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


class _FakeIntegrity:
    def __init__(self) -> None:
        self._skip = False
        self.success: List[tuple[str, str, str]] = []
        self.failed: List[tuple[str, str, str]] = []

    def compute_sha256(self, path: str) -> str:
        return f"hash::{Path(path).name}"

    def should_skip(self, file_hash: str) -> bool:
        return self._skip

    def mark_success(self, file_hash: str, file_path: str, message: str = "") -> None:
        self.success.append((file_hash, file_path, message))

    def mark_failed(self, file_hash: str, file_path: str, error_msg: str) -> None:
        self.failed.append((file_hash, file_path, error_msg))


class _FakeLoader:
    def __init__(self, image_path: Path) -> None:
        self._image_path = image_path

    def load(self, path: str, trace=None) -> Document:
        return Document(
            id="doc-001",
            text="intro [IMAGE: img-001] outro",
            metadata={
                "source_path": path,
                "images": [
                    {
                        "id": "img-001",
                        "path": str(self._image_path),
                        "page": 1,
                        "text_offset": 6,
                        "text_length": 16,
                        "position": {},
                    }
                ],
            },
        )


class _FakeChunker:
    def split_document(self, document: Document) -> List[Chunk]:
        return [
            Chunk(
                id="c0",
                text=document.text,
                metadata={"source_path": document.metadata["source_path"], "chunk_index": 0},
                start_offset=0,
                end_offset=len(document.text),
                source_ref=document.id,
            )
        ]


class _PassTransform:
    def transform(self, chunks: List[Chunk], trace=None) -> List[Chunk]:
        return chunks


class _FakeBatchProcessor:
    def process(self, chunks: List[Chunk], trace=None) -> List[ChunkRecord]:
        return [
            ChunkRecord(
                id=chunk.id,
                text=chunk.text,
                metadata=dict(chunk.metadata),
                dense_vector=[0.1, 0.2, 0.3],
                sparse_vector={"terms": {"intro": 1}, "doc_length": 1},
            )
            for chunk in chunks
        ]


class _FakeBM25Indexer:
    def __init__(self) -> None:
        self.calls = 0

    def build(self, records: List[ChunkRecord], *, rebuild: bool, persist: bool) -> None:
        self.calls += 1
        assert records
        assert rebuild is False
        assert persist is True


class _FakeVectorUpserter:
    def __init__(self) -> None:
        self.calls = 0
        self.last_collection: str = ""

    def upsert(self, records: List[ChunkRecord], *, collection: Optional[str] = None, trace=None) -> List[ChunkRecord]:
        self.calls += 1
        self.last_collection = collection or ""
        return records


class _FakeImageStorage:
    def __init__(self) -> None:
        self.saved: List[str] = []

    def save_image(
        self,
        image_id: str,
        image_bytes: bytes,
        *,
        collection: str,
        doc_hash: str = "",
        page_num=None,
        extension: str = ".png",
    ) -> str:
        self.saved.append(image_id)
        return f"/fake/{collection}/{image_id}{extension}"


@pytest.mark.integration
def test_pipeline_runs_full_flow_and_persists_success(tmp_path: Path) -> None:
    settings = _settings()
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"pdf-bytes")
    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"img-bytes")

    integrity = _FakeIntegrity()
    bm25 = _FakeBM25Indexer()
    upserter = _FakeVectorUpserter()
    image_storage = _FakeImageStorage()

    pipeline = IngestionPipeline(
        settings,
        integrity_checker=integrity,  # type: ignore[arg-type]
        loader=_FakeLoader(image_path),  # type: ignore[arg-type]
        chunker=_FakeChunker(),  # type: ignore[arg-type]
        transforms=[_PassTransform()],
        batch_processor=_FakeBatchProcessor(),  # type: ignore[arg-type]
        bm25_indexer=bm25,  # type: ignore[arg-type]
        vector_upserter=upserter,  # type: ignore[arg-type]
        image_storage=image_storage,  # type: ignore[arg-type]
    )
    trace = TraceContext(trace_type="ingestion")

    result = pipeline.run(str(file_path), collection="kb-a", trace=trace)

    assert result.skipped is False
    assert result.doc_id == "doc-001"
    assert result.chunk_count == 1
    assert result.record_count == 1
    assert result.image_count == 1
    assert bm25.calls == 1
    assert upserter.calls == 1
    assert image_storage.saved == ["img-001"]
    assert len(integrity.success) == 1
    assert integrity.failed == []
    stage_names = [item["stage"] for item in trace.stages]
    assert "integrity" in stage_names
    assert "load" in stage_names
    assert "split" in stage_names
    assert "transform" in stage_names
    assert "encode" in stage_names
    assert "store" in stage_names
    assert "image_store" in stage_names


@pytest.mark.integration
def test_pipeline_wraps_stage_error_and_marks_failed(tmp_path: Path) -> None:
    settings = _settings()
    file_path = tmp_path / "bad.pdf"
    file_path.write_bytes(b"pdf")
    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"img")
    integrity = _FakeIntegrity()

    class _BadChunker:
        def split_document(self, document: Document) -> List[Chunk]:
            raise ValueError("split failed")

    pipeline = IngestionPipeline(
        settings,
        integrity_checker=integrity,  # type: ignore[arg-type]
        loader=_FakeLoader(image_path),  # type: ignore[arg-type]
        chunker=_BadChunker(),  # type: ignore[arg-type]
        transforms=[_PassTransform()],
        batch_processor=_FakeBatchProcessor(),  # type: ignore[arg-type]
        bm25_indexer=_FakeBM25Indexer(),  # type: ignore[arg-type]
        vector_upserter=_FakeVectorUpserter(),  # type: ignore[arg-type]
        image_storage=_FakeImageStorage(),  # type: ignore[arg-type]
    )

    with pytest.raises(IngestionPipelineError, match=r"^\[split\]"):
        pipeline.run(str(file_path), collection="kb-a")
    assert len(integrity.failed) == 1


@pytest.mark.integration
def test_pipeline_trace_stages_include_elapsed_ms_and_method(tmp_path: Path) -> None:
    """F4: every main stage must record elapsed_ms and method fields."""
    settings = _settings()
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"pdf-bytes")
    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"img-bytes")

    pipeline = IngestionPipeline(
        settings,
        integrity_checker=_FakeIntegrity(),  # type: ignore[arg-type]
        loader=_FakeLoader(image_path),  # type: ignore[arg-type]
        chunker=_FakeChunker(),  # type: ignore[arg-type]
        transforms=[_PassTransform()],
        batch_processor=_FakeBatchProcessor(),  # type: ignore[arg-type]
        bm25_indexer=_FakeBM25Indexer(),  # type: ignore[arg-type]
        vector_upserter=_FakeVectorUpserter(),  # type: ignore[arg-type]
        image_storage=_FakeImageStorage(),  # type: ignore[arg-type]
    )
    trace = TraceContext(trace_type="ingestion")

    result = pipeline.run(str(file_path), collection="kb-a", trace=trace)
    assert result.skipped is False

    main_stages = {"integrity", "load", "split", "transform", "encode", "store", "image_store"}
    seen_stages: set = set()

    for entry in trace.stages:
        name = entry["stage"]
        seen_stages.add(name)
        if name in main_stages:
            assert "elapsed_ms" in entry, f"elapsed_ms missing in stage '{name}'"
            assert isinstance(entry["elapsed_ms"], (int, float)), f"elapsed_ms not numeric in '{name}'"
            if name == "load":
                assert "method" in entry
            if name == "split":
                assert entry["method"] == "recursive"
            if name == "store":
                assert entry["method"] == "chroma"

    for s in main_stages:
        assert s in seen_stages, f"main stage '{s}' not recorded"

    trace.finish()
    d = trace.to_dict()
    assert d["trace_type"] == "ingestion"
    assert d["total_elapsed_ms"] >= 0.0


def test_pipeline_on_progress_callback_called_for_each_stage(tmp_path: Path) -> None:
    """F5: on_progress callback receives each stage with current/total."""
    settings = _settings()
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"pdf-bytes")
    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"img-bytes")

    pipeline = IngestionPipeline(
        settings,
        integrity_checker=_FakeIntegrity(),  # type: ignore[arg-type]
        loader=_FakeLoader(image_path),  # type: ignore[arg-type]
        chunker=_FakeChunker(),  # type: ignore[arg-type]
        transforms=[_PassTransform()],
        batch_processor=_FakeBatchProcessor(),  # type: ignore[arg-type]
        bm25_indexer=_FakeBM25Indexer(),  # type: ignore[arg-type]
        vector_upserter=_FakeVectorUpserter(),  # type: ignore[arg-type]
        image_storage=_FakeImageStorage(),  # type: ignore[arg-type]
    )

    calls: List[Dict[str, Any]] = []

    def progress_callback(stage: str, current: int, total: int) -> None:
        calls.append({"stage": stage, "current": current, "total": total})

    result = pipeline.run(str(file_path), collection="kb-a", on_progress=progress_callback)
    assert result.skipped is False

    assert len(calls) > 0
    stage_names = {c["stage"] for c in calls}
    assert "integrity" in stage_names
    assert "load" in stage_names
    assert "split" in stage_names
    assert "transform" in stage_names
    assert "encode" in stage_names
    assert "store" in stage_names

    # Each progress call must have sensible current/total.
    for call in calls:
        assert call["current"] >= 0
        assert call["total"] >= 0
        assert isinstance(call["stage"], str)


def test_pipeline_on_progress_none_does_not_break(tmp_path: Path) -> None:
    """F5: when on_progress is None, pipeline must run normally."""
    settings = _settings()
    file_path = tmp_path / "sample.pdf"
    file_path.write_bytes(b"pdf-bytes")
    image_path = tmp_path / "img.png"
    image_path.write_bytes(b"img-bytes")

    pipeline = IngestionPipeline(
        settings,
        integrity_checker=_FakeIntegrity(),  # type: ignore[arg-type]
        loader=_FakeLoader(image_path),  # type: ignore[arg-type]
        chunker=_FakeChunker(),  # type: ignore[arg-type]
        transforms=[_PassTransform()],
        batch_processor=_FakeBatchProcessor(),  # type: ignore[arg-type]
        bm25_indexer=_FakeBM25Indexer(),  # type: ignore[arg-type]
        vector_upserter=_FakeVectorUpserter(),  # type: ignore[arg-type]
        image_storage=_FakeImageStorage(),  # type: ignore[arg-type]
    )

    # Should not raise when on_progress is None (default).
    result = pipeline.run(str(file_path), collection="kb-a")
    assert result.skipped is False
