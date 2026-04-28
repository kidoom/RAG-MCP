#!/usr/bin/env python3
"""CLI entrypoint for online query retrieval flow (D7)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.query_engine import (  # noqa: E402
    DenseRetriever,
    Fusion,
    HybridSearch,
    QueryProcessor,
    Reranker,
    SparseRetriever,
)
from core.settings import SettingsError, load_settings  # noqa: E402
from core.trace.trace_collector import TraceCollector  # noqa: E402
from core.trace.trace_context import TraceContext  # noqa: E402
from core.types import RetrievalResult  # noqa: E402
from observability.logger import write_trace  # noqa: E402


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run retrieval query from CLI")
    parser.add_argument("--query", required=True, help="User query text")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results to return")
    parser.add_argument("--collection", default="", help="Optional collection filter")
    parser.add_argument("--verbose", action="store_true", help="Print intermediate stage outputs")
    parser.add_argument("--no-rerank", action="store_true", help="Skip reranker stage")
    parser.add_argument("--settings", default="", help="Optional custom settings.yaml path")
    return parser.parse_args(argv)


def _build_filters(args: argparse.Namespace) -> Dict[str, Any]:
    filters: Dict[str, Any] = {}
    if args.collection.strip():
        filters["collection"] = args.collection.strip()
    return filters


def _format_result(index: int, item: RetrievalResult) -> str:
    md = item.metadata or {}
    source = md.get("source_path") or md.get("source") or "-"
    page = md.get("page") or md.get("page_number") or "-"
    text = " ".join(item.text.split())
    snippet = (text[:160] + "...") if len(text) > 160 else text
    return (
        f"[{index}] score={item.score:.4f} chunk_id={item.chunk_id}\n"
        f"    source={source} page={page}\n"
        f"    text={snippet}"
    )


def _print_stage(name: str, items: List[RetrievalResult]) -> None:
    print(f"\n=== {name} ({len(items)}) ===")
    for i, item in enumerate(items, start=1):
        print(_format_result(i, item))


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if args.top_k <= 0:
        print("[query] --top-k must be positive", file=sys.stderr)
        return 1

    try:
        settings = load_settings(args.settings or None)
    except SettingsError as exc:
        print(f"[query] settings error: {exc}", file=sys.stderr)
        return 1

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

    trace = TraceContext(trace_type="query")
    collector = TraceCollector(on_collect=write_trace)

    filters = _build_filters(args)
    try:
        if args.verbose:
            processed = query_processor.process(query=args.query, filters=filters)
            recall_k = max(args.top_k * 2, args.top_k)
            dense_results = dense.retrieve(
                query=processed.normalized_query,
                top_k=recall_k,
                filters=processed.filters,
            )
            sparse_results = sparse.retrieve(
                keywords=processed.keywords,
                top_k=recall_k,
            )
            fused_results = fusion.fuse(dense_results=dense_results, sparse_results=sparse_results, top_k=recall_k)
            hybrid_results = hybrid._apply_metadata_filters(fused_results, processed.filters)[: args.top_k]

            _print_stage("Dense", dense_results)
            _print_stage("Sparse", sparse_results)
            _print_stage("Fusion", fused_results)
            _print_stage("Hybrid", hybrid_results)
        else:
            hybrid_results = hybrid.search(
                query=args.query,
                top_k=args.top_k,
                filters=filters,
            )

        final_results = hybrid_results
        if not args.no_rerank and hybrid_results:
            final_results = reranker.rerank(
                query=args.query,
                candidates=hybrid_results,
                top_k=min(args.top_k, settings.rerank.top_k),
            )
            if args.verbose:
                _print_stage("Rerank", final_results)

    except Exception as exc:  # noqa: BLE001
        trace.record_stage("query_failed", error=str(exc))
        collector.collect(trace)
        print(f"[query] failed: {exc}", file=sys.stderr)
        return 1

    trace.record_stage(
        "query_done",
        query=args.query,
        result_count=len(final_results) if final_results else 0,
    )
    collector.collect(trace)

    if not final_results:
        print("未找到相关文档，请先运行 ingest.py 摄取数据。")
        return 0

    print(f"\n=== Final Top-{len(final_results)} ===")
    for i, item in enumerate(final_results, start=1):
        print(_format_result(i, item))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
