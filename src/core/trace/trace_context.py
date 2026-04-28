"""Trace context for ingestion / query pipelines (phase F)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TraceContext:
    """Collects stage records with timing for a single logical run (ingestion or query)."""

    trace_type: str = "ingestion"
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _stages: List[Dict[str, Any]] = field(default_factory=list, repr=False)
    _started_at: float = field(default_factory=time.monotonic, repr=False)
    _finished_at: Optional[float] = field(default=None, repr=False)

    def record_stage(self, name: str, **details: Any) -> None:
        """Append a named stage with current timestamp and arbitrary details."""
        entry: Dict[str, Any] = {
            "stage": name,
            "timestamp": time.monotonic(),
            **details,
        }
        self._stages.append(entry)

    @property
    def stages(self) -> List[Dict[str, Any]]:
        return list(self._stages)

    def finish(self) -> None:
        """Mark the trace as finished and record the completion timestamp."""
        if self._finished_at is None:
            self._finished_at = time.monotonic()

    def elapsed_ms(self, stage_name: Optional[str] = None) -> float:
        """Return elapsed milliseconds for a named stage or for the whole trace.

        For a named stage, looks for the first stage matching the given name and
        computes the delta from trace start to that stage's timestamp.  For the
        whole trace, uses finish time if already finished or current time otherwise.
        """
        if stage_name is not None:
            for entry in self._stages:
                if entry["stage"] == stage_name:
                    return (entry["timestamp"] - self._started_at) * 1000.0
            return 0.0

        end = self._finished_at if self._finished_at is not None else time.monotonic()
        return (end - self._started_at) * 1000.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the trace to a JSON-safe dictionary."""
        data: Dict[str, Any] = {
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "started_at": self._started_at,
            "finished_at": self._finished_at,
            "total_elapsed_ms": self.elapsed_ms(),
            "stages": list(self._stages),
        }
        return data
