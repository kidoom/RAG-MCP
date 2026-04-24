"""Batch processor that orchestrates dense and sparse encoding."""

from __future__ import annotations

import time
from typing import Callable, List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord

from .dense_encoder import DenseEncoder
from .sparse_encoder import SparseEncoder


class BatchProcessor:
    """Split chunks into batches and run dense/sparse encoders per batch."""

    def __init__(
        self,
        settings: Settings,
        dense_encoder: Optional[DenseEncoder] = None,
        sparse_encoder: Optional[SparseEncoder] = None,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' for BatchProcessor")
        self._settings = settings
        self._batch_size = max(1, int(settings.ingestion.batch_size))
        self._dense_encoder = dense_encoder or DenseEncoder(settings)
        self._sparse_encoder = sparse_encoder or SparseEncoder(settings)
        self._time_fn = time_fn or time.perf_counter

    def process(
        self, chunks: List[Chunk], trace: Optional[TraceContext] = None
    ) -> List[ChunkRecord]:
        if trace is not None:
            trace.record_stage(
                "batch_processor",
                chunk_count=len(chunks),
                batch_size=self._batch_size,
            )
        if not chunks:
            return []

        out: List[ChunkRecord] = []
        for batch_index, i in enumerate(range(0, len(chunks), self._batch_size)):
            batch = chunks[i : i + self._batch_size]
            t0 = self._time_fn()
            dense_records = self._dense_encoder.encode(batch, trace=trace)
            sparse_records = self._sparse_encoder.encode(batch, trace=trace)
            merged = self._merge_records(dense_records, sparse_records)
            out.extend(merged)
            elapsed_ms = (self._time_fn() - t0) * 1000.0
            if trace is not None:
                trace.record_stage(
                    "batch_processor_batch",
                    batch_index=batch_index,
                    batch_size=len(batch),
                    elapsed_ms=round(elapsed_ms, 3),
                )
        return out

    @staticmethod
    def _merge_records(
        dense_records: List[ChunkRecord], sparse_records: List[ChunkRecord]
    ) -> List[ChunkRecord]:
        if len(dense_records) != len(sparse_records):
            raise ValueError(
                "Dense/sparse record count mismatch: "
                f"{len(dense_records)} vs {len(sparse_records)}"
            )

        out: List[ChunkRecord] = []
        for d, s in zip(dense_records, sparse_records):
            if d.id != s.id:
                raise ValueError(
                    f"Dense/sparse record id mismatch: dense='{d.id}' sparse='{s.id}'"
                )
            out.append(
                ChunkRecord(
                    id=d.id,
                    text=d.text,
                    metadata=dict(d.metadata),
                    dense_vector=d.dense_vector,
                    sparse_vector=s.sparse_vector,
                )
            )
        return out
