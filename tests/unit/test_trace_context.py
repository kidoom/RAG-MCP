"""Unit tests for enhanced TraceContext (F1)."""

from __future__ import annotations

import json
import time

from core.trace import TraceContext, TraceCollector


def test_trace_context_has_trace_type_field() -> None:
    ctx = TraceContext(trace_type="query")
    assert ctx.trace_type == "query"

    ctx2 = TraceContext(trace_type="ingestion")
    assert ctx2.trace_type == "ingestion"


def test_trace_context_default_trace_type() -> None:
    ctx = TraceContext()
    assert ctx.trace_type == "ingestion"


def test_trace_context_stores_started_at() -> None:
    before = time.monotonic()
    ctx = TraceContext()
    after = time.monotonic()
    assert before <= ctx.to_dict()["started_at"] <= after


def test_record_stage_includes_timestamp() -> None:
    ctx = TraceContext()
    ctx.record_stage("load", doc_id="d1")
    entry = ctx.stages[0]
    assert entry["stage"] == "load"
    assert entry["doc_id"] == "d1"
    assert "timestamp" in entry


def test_finish_sets_finished_at() -> None:
    ctx = TraceContext()
    assert ctx.to_dict()["finished_at"] is None
    ctx.finish()
    assert ctx.to_dict()["finished_at"] is not None


def test_finish_is_idempotent() -> None:
    ctx = TraceContext()
    ctx.finish()
    first = ctx.to_dict()["finished_at"]
    ctx.finish()
    assert ctx.to_dict()["finished_at"] == first


def test_elapsed_ms_total() -> None:
    ctx = TraceContext()
    ctx.finish()
    elapsed = ctx.elapsed_ms()
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_elapsed_ms_for_named_stage() -> None:
    ctx = TraceContext()
    ctx.record_stage("load")
    elapsed = ctx.elapsed_ms("load")
    assert isinstance(elapsed, float)
    assert elapsed >= 0.0


def test_elapsed_ms_unknown_stage_returns_zero() -> None:
    ctx = TraceContext()
    assert ctx.elapsed_ms("nonexistent") == 0.0


def test_to_dict_json_serializable() -> None:
    ctx = TraceContext(trace_type="query")
    ctx.record_stage("search", method="dense", provider="openai")
    ctx.finish()
    data = ctx.to_dict()
    assert json.dumps(data)  # must not raise


def test_to_dict_contains_required_keys() -> None:
    ctx = TraceContext(trace_type="ingestion")
    ctx.record_stage("split", chunk_count=5)
    ctx.finish()
    data = ctx.to_dict()
    for key in ("trace_id", "trace_type", "started_at", "finished_at", "total_elapsed_ms", "stages"):
        assert key in data
    assert data["trace_type"] == "ingestion"
    assert len(data["stages"]) == 1


def test_trace_collector_finishes_and_stores_trace() -> None:
    collected: list = []

    def on_collect(data):
        collected.append(data)

    collector = TraceCollector(on_collect=on_collect)
    ctx = TraceContext(trace_type="query")
    ctx.record_stage("dense", method="openai")
    collector.collect(ctx)

    assert len(collector.traces) == 1
    assert len(collected) == 1
    stored = collector.traces[0]
    assert stored["trace_type"] == "query"
    assert stored["finished_at"] is not None
    assert stored["total_elapsed_ms"] >= 0.0
