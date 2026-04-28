"""Query processing utilities for retrieval stage (D1)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set


_DEFAULT_STOPWORDS: Set[str] = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}


@dataclass(frozen=True)
class ProcessedQuery:
    """Normalized query payload for downstream retrievers."""

    raw_query: str
    normalized_query: str
    keywords: List[str]
    filters: Dict[str, Any]


class QueryProcessor:
    # 查询预处理器，用于提取关键词和规范化查询过滤器 并返回处理后的查询  
    """Extract keywords and normalize query filters."""

    def __init__(self, stopwords: Optional[Set[str]] = None):
        self._stopwords = {w.lower() for w in (stopwords or _DEFAULT_STOPWORDS)}

    def process(
        self, query: str, filters: Optional[Mapping[str, Any]] = None
    ) -> ProcessedQuery:
        if not isinstance(query, str):
            raise TypeError("query must be a string")

        normalized_query = self._normalize_query(query)
        keywords = self._extract_keywords(normalized_query)
        normalized_filters = self._normalize_filters(filters)
        return ProcessedQuery(
            raw_query=query,
            normalized_query=normalized_query,
            keywords=keywords,
            filters=normalized_filters,
        )

    @staticmethod
    def _normalize_query(query: str) -> str:
        cleaned = re.sub(r"\s+", " ", query).strip()
        if not cleaned:
            raise ValueError("query must not be empty")
        return cleaned

    def _extract_keywords(self, normalized_query: str) -> List[str]:
        # Keep alphanumeric and CJK blocks as candidate tokens.
        tokens = re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+", normalized_query)
        keywords: List[str] = []
        seen: Set[str] = set()
        for token in tokens:
            t = token.lower().strip()
            if len(t) < 2:
                continue
            if t in self._stopwords:
                continue
            if t in seen:
                continue
            seen.add(t)
            keywords.append(t)

        if keywords:
            return keywords
        fallback = normalized_query.lower()
        return [fallback] if fallback else []

    @staticmethod
    def _normalize_filters(filters: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        if filters is None:
            return {}
        if not isinstance(filters, Mapping):
            raise TypeError("filters must be a mapping when provided")

        normalized: Dict[str, Any] = {}
        for key, value in filters.items():
            if not isinstance(key, str):
                continue
            k = key.strip()
            if not k:
                continue
            if value is None:
                continue
            if isinstance(value, str):
                v = value.strip()
                if not v:
                    continue
                normalized[k] = v
                continue
            if isinstance(value, list):
                cleaned = [item for item in value if item not in ("", None)]
                if cleaned:
                    normalized[k] = cleaned
                continue
            normalized[k] = value
        return normalized
