"""BM25 inverted index builder, persistence, and query API (C11)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.settings import REPO_ROOT
from core.types import ChunkRecord

DEFAULT_BM25_DIR = REPO_ROOT / "data" / "db" / "bm25"
DEFAULT_INDEX_FILE = "index.json"


class BM25Indexer:
    """Build/load/query a persisted BM25 inverted index."""

    def __init__(
        self,
        index_dir: Optional[str] = None,
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.index_dir = Path(index_dir) if index_dir else DEFAULT_BM25_DIR
        self.index_path = self.index_dir / DEFAULT_INDEX_FILE
        self.k1 = float(k1)
        self.b = float(b)

        self._doc_terms: Dict[str, Dict[str, int]] = {}
        self._doc_lengths: Dict[str, int] = {}
        self._doc_count: int = 0
        self._avg_doc_length: float = 0.0
        self._inverted_index: Dict[str, Dict[str, Any]] = {}

    @property
    def inverted_index(self) -> Dict[str, Dict[str, Any]]:
        return self._inverted_index

    @property
    def doc_count(self) -> int:
        return self._doc_count

    @property
    def avg_doc_length(self) -> float:
        return self._avg_doc_length

    def build(
        self,
        records: List[ChunkRecord],
        *,
        rebuild: bool = True,
        persist: bool = True,
    ) -> None:
        """Build index from sparse records.

        rebuild=True clears all previous docs.
        rebuild=False performs incremental update (insert/replace by chunk_id).
        """
        if rebuild:
            self._doc_terms.clear()
            self._doc_lengths.clear()

        for record in records:
            terms, doc_length = self._extract_sparse_terms(record)
            self._doc_terms[record.id] = terms
            self._doc_lengths[record.id] = doc_length

        self._recompute_index()
        if persist:
            self.save()

    def save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "k1": self.k1,
            "b": self.b,
            "doc_count": self._doc_count,
            "avg_doc_length": self._avg_doc_length,
            "doc_terms": self._doc_terms,
            "doc_lengths": self._doc_lengths,
            "inverted_index": self._inverted_index,
        }
        self.index_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )

    def load(self) -> bool:
        if not self.index_path.exists():
            return False
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.k1 = float(payload.get("k1", self.k1))
        self.b = float(payload.get("b", self.b))
        self._doc_count = int(payload.get("doc_count", 0))
        self._avg_doc_length = float(payload.get("avg_doc_length", 0.0))
        self._doc_terms = {
            str(doc_id): {str(t): int(v) for t, v in terms.items()}
            for doc_id, terms in (payload.get("doc_terms") or {}).items()
        }
        self._doc_lengths = {
            str(doc_id): int(length)
            for doc_id, length in (payload.get("doc_lengths") or {}).items()
        }
        self._inverted_index = dict(payload.get("inverted_index") or {})
        return True

    def query(self, keywords: List[str], top_k: int = 10) -> List[Dict[str, Any]]:
        if top_k <= 0:
            return []
        if not keywords or self._doc_count == 0:
            return []

        norm_terms = [kw.strip().lower() for kw in keywords if kw and kw.strip()]
        if not norm_terms:
            return []

        scores: Dict[str, float] = {}
        for term in norm_terms:
            term_entry = self._inverted_index.get(term)
            if not term_entry:
                continue

            idf = float(term_entry.get("idf", 0.0))
            postings = term_entry.get("postings", [])
            for posting in postings:
                chunk_id = str(posting["chunk_id"])
                tf = float(posting["tf"])
                doc_length = float(posting["doc_length"])
                score = self._bm25_term_score(tf=tf, doc_length=doc_length, idf=idf)
                scores[chunk_id] = scores.get(chunk_id, 0.0) + score

        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        return [
            {"chunk_id": chunk_id, "score": float(score)}
            for chunk_id, score in ranked[:top_k]
        ]

    def _recompute_index(self) -> None:
        self._doc_count = len(self._doc_terms)
        self._avg_doc_length = (
            (sum(self._doc_lengths.values()) / float(self._doc_count))
            if self._doc_count > 0
            else 0.0
        )

        df: Dict[str, int] = {}
        for terms in self._doc_terms.values():
            for term in terms.keys():
                df[term] = df.get(term, 0) + 1

        inverted_index: Dict[str, Dict[str, Any]] = {}
        for term in sorted(df.keys()):
            term_df = df[term]
            idf = self._compute_idf(self._doc_count, term_df)
            postings: List[Dict[str, Any]] = []
            for chunk_id in sorted(self._doc_terms.keys()):
                tf = self._doc_terms[chunk_id].get(term)
                if not tf:
                    continue
                postings.append(
                    {
                        "chunk_id": chunk_id,
                        "tf": int(tf),
                        "doc_length": int(self._doc_lengths[chunk_id]),
                    }
                )
            inverted_index[term] = {"idf": float(idf), "postings": postings}

        self._inverted_index = inverted_index

    @staticmethod
    def _compute_idf(doc_count: int, doc_freq: int) -> float:
        if doc_count <= 0 or doc_freq <= 0:
            return 0.0
        return math.log((doc_count - doc_freq + 0.5) / (doc_freq + 0.5))

    def _bm25_term_score(self, *, tf: float, doc_length: float, idf: float) -> float:
        denom = tf + self.k1 * (
            1.0
            - self.b
            + self.b * (doc_length / max(self._avg_doc_length, 1e-9))
        )
        if denom <= 0:
            return 0.0
        return idf * ((tf * (self.k1 + 1.0)) / denom)

    @staticmethod
    def _extract_sparse_terms(record: ChunkRecord) -> tuple[Dict[str, int], int]:
        sparse = record.sparse_vector or {}
        terms_raw = sparse.get("terms", {})
        doc_length_raw = sparse.get("doc_length", 0)
        if not isinstance(terms_raw, dict):
            raise ValueError(f"ChunkRecord[{record.id}] sparse_vector.terms must be a dict")
        terms: Dict[str, int] = {}
        for term, tf in terms_raw.items():
            term_norm = str(term).strip().lower()
            if not term_norm:
                continue
            tf_int = int(tf)
            if tf_int > 0:
                terms[term_norm] = tf_int

        doc_length = int(doc_length_raw) if int(doc_length_raw) >= 0 else 0
        return terms, doc_length
