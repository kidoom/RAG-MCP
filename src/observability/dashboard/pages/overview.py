"""System overview page — component configuration and data statistics."""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from core.settings import REPO_ROOT
from observability.dashboard.services.config_service import ConfigService


def _load_stats() -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "chroma_collections": 0,
        "chroma_entries": 0,
        "bm25_documents": 0,
        "images_stored": 0,
        "ingestion_records": 0,
    }
    try:
        import chromadb

        from core.settings import load_settings

        s = load_settings()
        client = chromadb.PersistentClient(path=s.vector_store.persist_directory)
        try:
            collection = client.get_collection(s.vector_store.collection_name)
            stats["chroma_collections"] = 1
            stats["chroma_entries"] = collection.count()
        except Exception:
            stats["chroma_collections"] = len(client.list_collections())
    except Exception:
        pass

    try:
        from ingestion.storage.bm25_indexer import BM25Indexer

        bm25 = BM25Indexer()
        if bm25.load():
            stats["bm25_documents"] = bm25.doc_count
    except Exception:
        pass

    try:
        import sqlite3

        img_db = REPO_ROOT / "data" / "db" / "image_index.db"
        if img_db.exists():
            conn = sqlite3.connect(str(img_db))
            row = conn.execute("SELECT COUNT(*) FROM image_index").fetchone()
            if row:
                stats["images_stored"] = row[0]
            conn.close()
    except Exception:
        pass

    try:
        import sqlite3

        hist_db = REPO_ROOT / "data" / "db" / "ingestion_history.db"
        if hist_db.exists():
            conn = sqlite3.connect(str(hist_db))
            row = conn.execute(
                "SELECT COUNT(*) FROM ingestion_history WHERE status='success'"
            ).fetchone()
            if row:
                stats["ingestion_records"] = row[0]
            conn.close()
    except Exception:
        pass

    return stats


def main() -> None:
    st.title("System Overview")
    st.caption("Component configuration and data statistics for the Modular RAG system.")

    cfg = ConfigService()

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.subheader("Component Configuration")
        cards = cfg.get_component_cards()

        # Display in rows of 2
        for i in range(0, len(cards), 2):
            row = st.columns(2)
            for j in range(2):
                idx = i + j
                if idx >= len(cards):
                    break
                card = cards[idx]
                with row[j]:
                    status_color = "green" if card["status"] == "active" else "gray"
                    st.markdown(
                        f"#### {card['icon']} {card['name']} "
                        f"<span style='color:{status_color};font-size:0.8em;'>●</span>",
                        unsafe_allow_html=True,
                    )
                    for label, value in card["fields"].items():
                        st.caption(f"**{label}:** {value}")

        # Ingestion config
        ingestion = cfg.get_ingestion_config()
        if ingestion:
            st.subheader("Ingestion Configuration")
            ingest_cols = st.columns(3)
            labels = list(ingestion.items())
            for i, (label, value) in enumerate(labels):
                with ingest_cols[i % 3]:
                    st.caption(f"**{label}:** {value}")

    with col_right:
        st.subheader("Data Statistics")
        stats = _load_stats()

        st.metric("Chroma Entries", stats["chroma_entries"])
        st.metric("BM25 Documents", stats["bm25_documents"])
        st.metric("Images Stored", stats["images_stored"])
        st.metric("Ingestion Records", stats["ingestion_records"])

        st.divider()

        st.subheader("Paths")
        try:
            s = cfg.settings
            st.caption(f"**Vector Store:** `{s.vector_store.persist_directory}`")
            st.caption(f"**Trace File:** `{s.observability.trace_file}`")
        except Exception:
            st.caption("Settings not available")


main()
