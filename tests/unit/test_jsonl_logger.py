"""Unit tests for JSON Lines structured logger (F2)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import pytest

from observability.logger import (
    JSONFormatter,
    get_logger,
    get_trace_logger,
    write_trace,
)


def test_json_formatter_produces_valid_json() -> None:
    fmt = JSONFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    line = fmt.format(record)
    data = json.loads(line)
    assert data["level"] == "INFO"
    assert data["logger"] == "test"
    assert data["message"] == "hello world"
    assert "timestamp" in data


def test_json_formatter_includes_exception() -> None:
    fmt = JSONFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="", lineno=1,
            msg="error", args=(), exc_info=("ValueError", ValueError("boom"), None),
        )
    line = fmt.format(record)
    data = json.loads(line)
    assert "exception" in data


def test_get_trace_logger_outputs_json() -> None:
    from io import StringIO

    logger = get_trace_logger("test_trace")
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    # Temporarily swap handler
    logger.handlers.clear()
    logger.addHandler(handler)

    logger.info("trace event %d", 42)
    line = stream.getvalue().strip()
    data = json.loads(line)
    assert data["message"] == "trace event 42"


def test_write_trace_writes_json_line_to_file() -> None:
    trace_dict = {
        "trace_id": "abc-123",
        "trace_type": "query",
        "started_at": 1714200000.0,
        "finished_at": 1714200001.0,
        "total_elapsed_ms": 1000.0,
        "stages": [
            {"stage": "dense", "timestamp": 1714200000.0, "method": "openai"},
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "traces.jsonl")
        write_trace(trace_dict, file_path=file_path)

        assert Path(file_path).exists()
        content = Path(file_path).read_text(encoding="utf-8").strip()
        data = json.loads(content)
        assert data["trace_id"] == "abc-123"
        assert data["trace_type"] == "query"


def test_write_trace_appends_multiple_lines() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = os.path.join(tmpdir, "traces.jsonl")
        write_trace({"trace_id": "t1", "trace_type": "query"}, file_path=file_path)
        write_trace({"trace_id": "t2", "trace_type": "ingestion"}, file_path=file_path)

        lines = Path(file_path).read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["trace_id"] == "t1"
        assert json.loads(lines[1])["trace_id"] == "t2"
