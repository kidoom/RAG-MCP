"""Build MCP tool response payloads from retrieval results."""

from __future__ import annotations

from typing import Any, Dict, List

from core.types import RetrievalResult

from .citation_generator import CitationGenerator
from .multimodal_assembler import MultimodalAssembler


class ResponseBuilder:
    """Build MCP content + structured citations."""

    def __init__(
        self,
        citation_generator: CitationGenerator | None = None,
        multimodal_assembler: MultimodalAssembler | None = None,
    ) -> None:
        self._citation_generator = citation_generator or CitationGenerator()
        self._multimodal_assembler = multimodal_assembler or MultimodalAssembler()

    def build(self, retrieval_results: List[RetrievalResult], query: str) -> Dict[str, Any]:
        citations = self._citation_generator.generate(retrieval_results)
        markdown = self._build_markdown(query=query, retrieval_results=retrieval_results)

        image_content = self._multimodal_assembler.assemble(retrieval_results)
        return {
            "content": [{"type": "text", "text": markdown}, *image_content],
            "structuredContent": {"query": query, "citations": citations},
        }

    @staticmethod
    def _build_markdown(query: str, retrieval_results: List[RetrievalResult]) -> str:
        if not retrieval_results:
            return "未找到相关文档，请先运行 ingest.py 摄取数据。"

        lines: List[str] = [f"查询：{query}", "", "检索结果："]
        for idx, item in enumerate(retrieval_results, start=1):
            md = item.metadata or {}
            source = md.get("source_path") or md.get("source") or "unknown"
            page = md.get("page") or md.get("page_number") or "-"
            text = " ".join(item.text.split())
            snippet = (text[:180] + "...") if len(text) > 180 else text
            lines.append(f"{idx}. {snippet} [{idx}]")
            lines.append(f"   - source: {source}")
            lines.append(f"   - page: {page}")
            lines.append(f"   - chunk_id: {item.chunk_id}")
        return "\n".join(lines)
