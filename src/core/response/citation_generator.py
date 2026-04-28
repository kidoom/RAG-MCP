"""Generate structured citations from retrieval results."""

from __future__ import annotations

from typing import Any, Dict, List

from core.types import RetrievalResult


class CitationGenerator:
    """Create stable structured citations for MCP responses."""

    def generate(self, retrieval_results: List[RetrievalResult]) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        for item in retrieval_results:
            md = item.metadata or {}
            citations.append(
                {
                    "source": md.get("source_path") or md.get("source") or "unknown",
                    "page": md.get("page") or md.get("page_number"),
                    "chunk_id": item.chunk_id,
                    "score": float(item.score),
                }
            )
        return citations
