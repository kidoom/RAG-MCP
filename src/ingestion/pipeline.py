"""Ingestion pipeline orchestration (C14 / F4 / F5)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.settings import REPO_ROOT, Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord, Document
from ingestion.chunking import DocumentChunker
from ingestion.embedding import BatchProcessor
from ingestion.storage import BM25Indexer, ImageStorage, VectorUpserter
from ingestion.transform import ChunkRefiner, ImageCaptioner, MetadataEnricher
from libs.loader import BaseLoader, FileIntegrityChecker, PdfLoader, SQLiteIntegrityChecker


class IngestionPipelineError(RuntimeError):
    """Error with stage context for easier diagnosis."""

    def __init__(self, stage: str, file_path: str, message: str):
        self.stage = stage
        self.file_path = file_path
        super().__init__(f"[{stage}] {file_path}: {message}")


@dataclass(frozen=True)
class IngestionResult:
    """Structured ingestion result."""

    file_path: str
    file_hash: str
    skipped: bool
    doc_id: str
    chunk_count: int
    record_count: int
    image_count: int


# Signature for the on_progress callback (F5).
ProgressCallback = Callable[[str, int, int], None]


class IngestionPipeline:
    """Run integrity -> load -> split -> transform -> encode -> store.

    Supports optional trace context (F4) and progress callback (F5).
    """

    def __init__(
        self,
        settings: Settings,
        *,
        integrity_checker: Optional[FileIntegrityChecker] = None,
        loader: Optional[BaseLoader] = None,
        chunker: Optional[DocumentChunker] = None,
        transforms: Optional[Sequence[Callable[[List[Chunk], Optional[TraceContext]], List[Chunk]]]] = None,
        batch_processor: Optional[BatchProcessor] = None,
        bm25_indexer: Optional[BM25Indexer] = None,
        vector_upserter: Optional[VectorUpserter] = None,
        image_storage: Optional[ImageStorage] = None,
    ):
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' for IngestionPipeline")

        self._settings = settings
        self._integrity_checker = integrity_checker or SQLiteIntegrityChecker()
        self._loader = loader or PdfLoader()
        self._chunker = chunker or DocumentChunker(settings)
        self._transforms = list(transforms) if transforms is not None else [
            ChunkRefiner(settings),
            MetadataEnricher(settings),
            ImageCaptioner(settings),
        ]
        self._batch_processor = batch_processor or BatchProcessor(settings)
        self._bm25_indexer = bm25_indexer or BM25Indexer()
        self._vector_upserter = vector_upserter or VectorUpserter(settings)
        self._image_storage = image_storage or ImageStorage()

    # ---------------------------------------------------------------- public API

    def run(
        self,
        file_path: str,
        *,
        collection: Optional[str] = None,
        force: bool = False,
        trace: Optional[TraceContext] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> IngestionResult:
        """Execute full ingestion flow for one document.

        Args:
            file_path: Path to the source file.
            collection: Target collection name.
            force: If True, re-ingest even if the file hash is unchanged.
            trace: Optional trace context for observability (F4).
            on_progress: Optional callback(stage, current, total) for UI (F5).
        """
        resolved_file = str(Path(file_path).resolve())
        trace_ctx = trace or TraceContext(trace_type="ingestion")
        target_collection = (
            collection.strip()
            if isinstance(collection, str) and collection.strip()
            else self._settings.vector_store.collection_name
        )

        _fire(on_progress, "integrity", 0, 1)

        file_hash = self._stage_integrity(resolved_file, force, trace_ctx)
        if file_hash is None:
            return IngestionResult(
                file_path=resolved_file,
                file_hash="",
                skipped=True,
                doc_id="",
                chunk_count=0,
                record_count=0,
                image_count=0,
            )

        try:
            _fire(on_progress, "load", 0, 1)
            document = self._stage_load(resolved_file, trace_ctx)
            _fire(on_progress, "load", 1, 1)

            chunk_count_total = _estimate_chunk_count(document)
            _fire(on_progress, "split", 0, chunk_count_total)
            chunks = self._stage_split(document, trace_ctx)
            _fire(on_progress, "split", len(chunks), len(chunks))

            transform_count = len(self._transforms)
            for i, _transform in enumerate(self._transforms):
                _fire(on_progress, "transform", i, transform_count)
            transformed = self._stage_transform(chunks, trace_ctx)
            _fire(on_progress, "transform", transform_count, transform_count)

            _fire(on_progress, "encode", 0, len(transformed))
            records = self._stage_encode(transformed, trace_ctx)
            _fire(on_progress, "encode", len(records), len(records))

            _fire(on_progress, "store", 0, len(records))
            stored_records = self._stage_store(records, target_collection, trace_ctx)
            _fire(on_progress, "store", len(stored_records), len(stored_records))

            image_count = self._stage_store_images(document, target_collection, trace_ctx)

            self._integrity_checker.mark_success(
                file_hash=file_hash,
                file_path=resolved_file,
                message=f"doc_id={document.id};chunks={len(transformed)};records={len(stored_records)}",
            )
            trace_ctx.record_stage(
                "pipeline_done",
                file_path=resolved_file,
                doc_id=document.id,
                chunk_count=len(transformed),
                record_count=len(stored_records),
                image_count=image_count,
            )
            return IngestionResult(
                file_path=resolved_file,
                file_hash=file_hash,
                skipped=False,
                doc_id=document.id,
                chunk_count=len(transformed),
                record_count=len(stored_records),
                image_count=image_count,
            )
        except Exception as exc:  # noqa: BLE001
            self._integrity_checker.mark_failed(
                file_hash=file_hash,
                file_path=resolved_file,
                error_msg=str(exc),
            )
            raise

    # --------------------------------------------------------------- stages (F4)

    def _stage_integrity(
        self, file_path: str, force: bool, trace: TraceContext
    ) -> Optional[str]:
        stage = "integrity"
        t0 = time.monotonic()
        try:
            file_hash = self._integrity_checker.compute_sha256(file_path)
            should_skip = (not force) and self._integrity_checker.should_skip(file_hash)
            trace.record_stage(
                stage,
                file_path=file_path,
                file_hash=file_hash,
                force=force,
                skipped=should_skip,
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                method="sha256+sqlite",
            )
            return None if should_skip else file_hash
        except Exception as exc:  # noqa: BLE001
            raise IngestionPipelineError(stage, file_path, str(exc)) from exc

    def _stage_load(self, file_path: str, trace: TraceContext) -> Document:
        stage = "load"
        t0 = time.monotonic()
        try:
            document = self._loader.load(file_path, trace=trace)
            trace.record_stage(
                stage,
                doc_id=document.id,
                text_chars=len(document.text),
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                method=getattr(self._loader, "__class__", type(self._loader)).__name__,
            )
            return document
        except Exception as exc:  # noqa: BLE001
            raise IngestionPipelineError(stage, file_path, str(exc)) from exc

    def _stage_split(self, document: Document, trace: TraceContext) -> List[Chunk]:
        stage = "split"
        t0 = time.monotonic()
        try:
            chunks = self._chunker.split_document(document)
            trace.record_stage(
                stage,
                chunk_count=len(chunks),
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                method=self._settings.ingestion.splitter,
            )
            return chunks
        except Exception as exc:  # noqa: BLE001
            raise IngestionPipelineError(
                stage, document.metadata.get("source_path", document.id), str(exc)
            ) from exc

    def _stage_transform(self, chunks: List[Chunk], trace: TraceContext) -> List[Chunk]:
        stage = "transform"
        t0 = time.monotonic()
        output = chunks
        try:
            for transform in self._transforms:
                transform_name = transform.__class__.__name__
                t_step = time.monotonic()
                output = transform.transform(output, trace=trace)  # type: ignore[attr-defined]
                trace.record_stage(
                    "transform_step",
                    transform=transform_name,
                    chunk_count=len(output),
                    elapsed_ms=(time.monotonic() - t_step) * 1000.0,
                )
            trace.record_stage(
                stage,
                chunk_count=len(output),
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
            )
            return output
        except Exception as exc:  # noqa: BLE001
            raise IngestionPipelineError(stage, "<in-memory>", str(exc)) from exc

    def _stage_encode(self, chunks: List[Chunk], trace: TraceContext) -> List[ChunkRecord]:
        stage = "encode"
        t0 = time.monotonic()
        try:
            records = self._batch_processor.process(chunks, trace=trace)
            trace.record_stage(
                stage,
                record_count=len(records),
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                method=f"{self._settings.embedding.provider}+bm25",
            )
            return records
        except Exception as exc:  # noqa: BLE001
            raise IngestionPipelineError(stage, "<in-memory>", str(exc)) from exc

    def _stage_store(
        self,
        records: List[ChunkRecord],
        collection: str,
        trace: TraceContext,
    ) -> List[ChunkRecord]:
        stage = "store"
        t0 = time.monotonic()
        try:
            # Upsert first so deterministic chunk_ids are computed (VectorUpserter
            # owns the canonical id generation per C12).  Pass the returned records
            # with stable ids to BM25 so both stores share the same chunk_id space.
            upserted = self._vector_upserter.upsert(
                records, collection=collection, trace=trace
            )
            self._bm25_indexer.build(upserted, rebuild=False, persist=True)
            trace.record_stage(
                stage,
                record_count=len(upserted),
                elapsed_ms=(time.monotonic() - t0) * 1000.0,
                method=self._settings.vector_store.provider,
            )
            return upserted
        except Exception as exc:  # noqa: BLE001
            raise IngestionPipelineError(stage, "<in-memory>", str(exc)) from exc

    def _stage_store_images(
        self, document: Document, collection: str, trace: TraceContext
    ) -> int:
        stage = "image_store"
        t0 = time.monotonic()
        images = document.metadata.get("images")
        if not isinstance(images, list) or not images:
            trace.record_stage(stage, stored_count=0, elapsed_ms=0.0)
            return 0

        stored = 0
        for image in images:
            if not isinstance(image, dict):
                continue
            image_id = image.get("id")
            image_path = image.get("path")
            if not isinstance(image_id, str) or not image_id.strip():
                continue
            if not isinstance(image_path, str) or not image_path.strip():
                continue

            resolved = Path(image_path)
            if not resolved.is_absolute():
                resolved = (REPO_ROOT / image_path).resolve()
            if not resolved.exists():
                continue

            image_bytes = resolved.read_bytes()
            suffix = resolved.suffix or ".png"
            self._image_storage.save_image(
                image_id=image_id,
                image_bytes=image_bytes,
                collection=collection,
                doc_hash=document.id,
                page_num=image.get("page"),
                extension=suffix,
            )
            stored += 1

        trace.record_stage(
            stage,
            stored_count=stored,
            elapsed_ms=(time.monotonic() - t0) * 1000.0,
        )
        return stored


# ------------------------------------------------------------------- helpers

def _fire(
    on_progress: Optional[ProgressCallback], stage: str, current: int, total: int
) -> None:
    """Invoke progress callback if set (F5)."""
    if on_progress is not None:
        on_progress(stage, current, total)


def _estimate_chunk_count(document: Document) -> int:
    """Rough chunk-count estimate before splitting (for progress reporting)."""
    size = getattr(document, "chunk_size", None)
    if isinstance(size, int) and size > 0:
        return max(1, len(document.text) // size)
    return max(1, len(document.text) // 500)
