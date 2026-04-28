"""Trace collector — gathers finished traces and persists them (F1)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .trace_context import TraceContext


class TraceCollector:
    """Collect finished TraceContext objects and optionally persist via callback."""

    def __init__(self, on_collect: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
        self._traces: List[Dict[str, Any]] = []
        self._on_collect = on_collect

    def collect(self, trace: TraceContext) -> None:
        """Finish the trace (if not already) and persist it."""
        trace.finish()
        data = trace.to_dict()
        self._traces.append(data)
        if self._on_collect is not None:
            self._on_collect(data)

    @property
    def traces(self) -> List[Dict[str, Any]]:
        return list(self._traces)
