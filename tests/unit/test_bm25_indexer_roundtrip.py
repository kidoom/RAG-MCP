"""Unit tests for BM25Indexer (C11)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List

import pytest

from core.types import ChunkRecord
from ingestion.storage import BM25Indexer


def _record(
    chunk_id: str,
    terms: Dict[str, int],
    *,
    doc_length: int,
    source_path: str = "/docs/demo.pdf",
) -> ChunkRecord:
    return ChunkRecord(
        id=chunk_id,
        text=f"text-{chunk_id}",
        metadata={"source_path": source_path},
        dense_vector=None,
        sparse_vector={
            "terms": terms,
            "term_weights": {},
            "doc_length": doc_length,
            "unique_terms": len(terms),
        },
    )


def _sample_records() -> List[ChunkRecord]:
    return [
        _record("c1", {"apple": 2, "banana": 1}, doc_length=3),
        _record("c2", {"banana": 2, "carrot": 1}, doc_length=3),
        _record("c3", {"apple": 1}, doc_length=1),
    ]


def test_bm25_indexer_roundtrip_build_load_query(tmp_path: Path) -> None:
    index_dir = tmp_path / "bm25"
    indexer = BM25Indexer(index_dir=str(index_dir))
    indexer.build(_sample_records(), rebuild=True, persist=True)
    assert (index_dir / "index.json").exists()

    loaded = BM25Indexer(index_dir=str(index_dir))
    assert loaded.load() is True
    assert loaded.doc_count == 3

    q1 = loaded.query(["apple"], top_k=3)
    q2 = loaded.query(["apple"], top_k=3)
    assert [x["chunk_id"] for x in q1] == [x["chunk_id"] for x in q2]
    assert q1 and q1[0]["chunk_id"] in {"c1", "c3"}


def test_bm25_indexer_idf_matches_formula() -> None:
    indexer = BM25Indexer(index_dir=".")
    indexer.build(_sample_records(), rebuild=True, persist=False)

    expected = math.log((3 - 2 + 0.5) / (2 + 0.5))
    got = float(indexer.inverted_index["apple"]["idf"])
    assert got == pytest.approx(expected)


def test_bm25_indexer_incremental_update_adds_new_doc(tmp_path: Path) -> None:
    indexer = BM25Indexer(index_dir=str(tmp_path / "bm25"))
    indexer.build(_sample_records()[:2], rebuild=True, persist=False)
    assert indexer.doc_count == 2

    indexer.build([_record("c3", {"dragonfruit": 2}, doc_length=2)], rebuild=False, persist=False)
    assert indexer.doc_count == 3
    out = indexer.query(["dragonfruit"], top_k=2)
    assert [x["chunk_id"] for x in out] == ["c3"]


def test_bm25_indexer_rebuild_resets_old_docs(tmp_path: Path) -> None:
    indexer = BM25Indexer(index_dir=str(tmp_path / "bm25"))
    indexer.build(_sample_records(), rebuild=True, persist=False)
    assert indexer.doc_count == 3

    indexer.build([_record("new1", {"pear": 1}, doc_length=1)], rebuild=True, persist=False)
    assert indexer.doc_count == 1
    assert indexer.query(["apple"], top_k=3) == []
    assert [x["chunk_id"] for x in indexer.query(["pear"], top_k=3)] == ["new1"]


def test_bm25_indexer_handles_empty_and_invalid_inputs(tmp_path: Path) -> None:
    indexer = BM25Indexer(index_dir=str(tmp_path / "bm25"))
    indexer.build([_record("empty", {}, doc_length=0)], rebuild=True, persist=False)
    assert indexer.doc_count == 1
    assert indexer.query([], top_k=5) == []
    assert indexer.query(["anything"], top_k=5) == []
    assert indexer.query(["anything"], top_k=0) == []


def test_bm25_indexer_stable_sorting_on_score_ties(tmp_path: Path) -> None:
    indexer = BM25Indexer(index_dir=str(tmp_path / "bm25"))
    indexer.build(
        [
            _record("a", {"term": 1}, doc_length=1),
            _record("b", {"term": 1}, doc_length=1),
        ],
        rebuild=True,
        persist=False,
    )
    out = indexer.query(["term"], top_k=10)
    assert [x["chunk_id"] for x in out] == ["a", "b"]


def test_bm25_indexer_raises_for_invalid_sparse_terms(tmp_path: Path) -> None:
    bad = ChunkRecord(
        id="bad",
        text="bad",
        metadata={"source_path": "/docs/bad.pdf"},
        sparse_vector={"terms": ["not-a-dict"], "doc_length": 1},
    )
    indexer = BM25Indexer(index_dir=str(tmp_path / "bm25"))
    with pytest.raises(ValueError, match="terms must be a dict"):
        indexer.build([bad], rebuild=True, persist=False)
