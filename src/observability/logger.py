"""Observability module for logging and tracing.

This module provides centralized logging configuration, JSON Lines structured logging,
and trace persistence utilities.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_logger: Optional[logging.Logger] = None
_trace_logger: Optional[logging.Logger] = None


class JSONFormatter(logging.Formatter):
    """Custom logging Formatter that outputs JSON Lines."""

    def format(self, record: logging.LogRecord) -> str:
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False)


def get_logger(name: str = "modular_rag_mcp") -> logging.Logger:
    """Get or create the main application logger (stderr, plain text)."""
    global _logger

    if _logger is None:
        _logger = logging.getLogger(name)
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            "[%(levelname)s] %(name)s: %(message)s",
        )
        handler.setFormatter(formatter)
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)

    return _logger


def get_trace_logger(name: str = "trace") -> logging.Logger:
    """Get or create the trace logger configured with JSON Lines output to stderr."""
    global _trace_logger

    if _trace_logger is None:
        _trace_logger = logging.getLogger(name)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JSONFormatter())
        _trace_logger.addHandler(handler)
        _trace_logger.setLevel(logging.INFO)
        _trace_logger.propagate = False

    return _trace_logger


def write_trace(trace_dict: Dict[str, Any], file_path: Optional[str] = None) -> None:
    """Write a trace dictionary as one JSON line to a file and to the trace logger.

    Args:
        trace_dict: The serialized trace (from TraceContext.to_dict()).
        file_path: Path to a JSON Lines file. Defaults to REPO_ROOT/logs/traces.jsonl.
    """
    line = json.dumps(trace_dict, ensure_ascii=False)

    if file_path is None:
        from core.settings import REPO_ROOT

        file_path = str(REPO_ROOT / "logs" / "traces.jsonl")

    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")

    trace_logger = get_trace_logger()
    trace_logger.info("trace persisted", extra={"trace_id": trace_dict.get("trace_id", "")})


def set_log_level(level: str) -> None:
    """Set the log level for the main logger.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger = get_logger()
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)
