"""Sparse encoder producing BM25-ready term statistics per chunk."""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
_STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
    "on",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
}


class SparseEncoder:
    """Build sparse term statistics used by the BM25 indexer in C11."""

    def __init__(self, settings: Settings):
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' for SparseEncoder")
        self._settings = settings

    def encode(
        self, chunks: List[Chunk], trace: Optional[TraceContext] = None
    ) -> List[ChunkRecord]:
        if trace is not None:
            trace.record_stage("sparse_encoder", chunk_count=len(chunks), method="bm25_stats")

        out: List[ChunkRecord] = []
        for chunk in chunks:
            sparse = self._encode_text(chunk.text)
            out.append(
                ChunkRecord(
                    id=chunk.id,
                    text=chunk.text,
                    metadata=dict(chunk.metadata),
                    dense_vector=None,
                    sparse_vector=sparse,
                )
            )
        return out

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens = [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]
        return [t for t in tokens if t and t not in _STOPWORDS]

    def _encode_text(self, text: str) -> Dict[str, object]:
        tokens = self._tokenize(text)
        if not tokens:
            return {"terms": {}, "term_weights": {}, "doc_length": 0, "unique_terms": 0}

        counts = Counter(tokens)
        doc_length = len(tokens)
        sorted_terms = sorted(counts.keys())
        terms = {term: int(counts[term]) for term in sorted_terms}
        term_weights = {term: float(counts[term]) / float(doc_length) for term in sorted_terms}

        return {
            "terms": terms,
            "term_weights": term_weights,
            "doc_length": doc_length,
            "unique_terms": len(terms),
        }
