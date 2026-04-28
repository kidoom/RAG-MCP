"""MCP tool: query_knowledge_hub."""

from __future__ import annotations

from typing import Any, List

from core.query_engine import (
    DenseRetriever,
    Fusion,
    HybridSearch,
    QueryProcessor,
    Reranker,
    SparseRetriever,
)
from core.response import ResponseBuilder
from core.settings import load_settings
from core.types import RetrievalResult



def query_knowledge_hub(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Run hybrid retrieval + reranker and return MCP response payload."""
    query = str(arguments.get("query", "")).strip()
    if not query:
        raise ValueError("query is required")

    top_k = int(arguments.get("top_k", 5))
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    top_k = min(top_k, 20)

    builder = ResponseBuilder()

    try:
        settings = load_settings()
        query_processor = QueryProcessor()
        dense = DenseRetriever(settings=settings)
        sparse = SparseRetriever(settings=settings)
        fusion = Fusion(settings=settings)
        hybrid = HybridSearch(
            settings=settings,
            query_processor=query_processor,
            dense_retriever=dense,
            sparse_retriever=sparse,
            fusion=fusion,
        )
        reranker = Reranker(settings=settings)

        results: List[RetrievalResult] = hybrid.search(query=query, top_k=top_k)
        if results:
            results = reranker.rerank(
                query=query,
                candidates=results,
                top_k=min(top_k, settings.rerank.top_k),
            )
    except Exception as exc:
        from observability.logger import get_logger
        get_logger("query_knowledge_hub").exception("Retrieval failed")
        results = []
        results.append(RetrievalResult(
            chunk_id="error",
            score=0.0,
            text=f"检索失败: {exc}",
            metadata={"error": str(exc)},
        ))

    return builder.build(retrieval_results=results, query=query)
