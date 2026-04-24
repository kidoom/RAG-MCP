"""Minimal trace context for ingestion / query pipelines (expanded in phase F)."""
# TraceContext 类用于收集 ingestion 或 query 过程中的阶段记录。它包含 trace_type（ingestion 或 query）、trace_id（唯一标识符）和 _stages（阶段记录列表）。
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class TraceContext:
    """Collects stage records for a single logical run (ingestion or query)."""
# trace_type：记录 ingestion 或 query 类型
# trace_id：唯一标识符
# _stages：阶段记录列表
    trace_type: str = "ingestion"
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    _stages: List[Dict[str, Any]] = field(default_factory=list, repr=False)

    def record_stage(self, name: str, **details: Any) -> None:
        """Append a named stage with arbitrary JSON-serializable details."""
        entry: Dict[str, Any] = {"stage": name, **details}
        self._stages.append(entry)

    @property
    def stages(self) -> List[Dict[str, Any]]:
        return list(self._stages)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "trace_type": self.trace_type,
            "stages": list(self._stages),
        }
