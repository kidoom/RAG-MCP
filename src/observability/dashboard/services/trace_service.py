"""Trace data service — parse traces.jsonl for the Dashboard UI (G5/G6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.settings import REPO_ROOT, load_settings

DEFAULT_TRACE_FILE = REPO_ROOT / "logs" / "traces.jsonl"


class TraceService:
    """Read and parse traces.jsonl into Trace objects for display."""

    def __init__(self, trace_file: Optional[str] = None) -> None:
        if trace_file is not None:
            self._trace_path = Path(trace_file)
        else:
            try:
                s = load_settings()
                self._trace_path = Path(s.observability.trace_file)
            except Exception:
                self._trace_path = DEFAULT_TRACE_FILE
        if not self._trace_path.is_absolute():
            self._trace_path = REPO_ROOT / self._trace_path

    def load_traces(
        self,
        trace_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Load traces from the JSONL file, optionally filtered by type.

        Returns traces sorted by started_at descending.
        """
        if not self._trace_path.exists():
            return []

        traces: List[Dict[str, Any]] = []
        try:
            with self._trace_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if trace_type is None or data.get("trace_type") == trace_type:
                        traces.append(data)
        except Exception:
            return []

        traces.sort(key=lambda t: t.get("started_at", 0), reverse=True)
        return traces[:limit]

    def get_trace_detail(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Get a single trace by ID."""
        traces = self.load_traces()
        for t in traces:
            if t.get("trace_id") == trace_id:
                return t
        return None

    @staticmethod
    def stage_label(slug: str) -> str:
        """Human-readable label for internal stage names."""
        labels: Dict[str, str] = {
            "integrity": "Integrity Check",
            "load": "Document Load",
            "split": "Text Split",
            "transform": "Transform",
            "transform_step": "Transform Step",
            "encode": "Embedding Encode",
            "store": "Vector/BF Store",
            "image_store": "Image Store",
            "pipeline_done": "Pipeline Done",
            "query_rewrite": "Query Rewrite",
            "dense_search": "Dense Search",
            "sparse_search": "Sparse Search",
            "fusion": "RRF Fusion",
            "rerank": "Rerank",
            "response_build": "Response Build",
            "query_done": "Query Done",
        }
        return labels.get(slug, slug.replace("_", " ").title())

    @staticmethod
    def extract_stage_times(
        stages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Extract stage name and elapsed_ms for waterfall display."""
        result = []
        for s in stages:
            name = TraceService.stage_label(s.get("stage", "unknown"))
            elapsed = s.get("elapsed_ms")
            if elapsed is None:
                continue
            result.append({
                "stage": name,
                "elapsed_ms": float(elapsed),
                "raw": s.get("stage", ""),
            })
        return result

    def get_stage_dataframe(self, stages: List[Dict[str, Any]]) -> Any:
        """Convert stage data to a pandas DataFrame for charting."""
        import pandas as pd

        rows = self.extract_stage_times(stages)
        if not rows:
            return None
        return pd.DataFrame(rows)
