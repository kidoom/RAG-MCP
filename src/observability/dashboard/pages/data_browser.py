"""Data browser page — document list, chunk detail, and image preview."""

from __future__ import annotations

import hashlib

import streamlit as st

from observability.dashboard.services.data_service import DataService

COLLECTION_OPTIONS_LIMIT = 50


def _safe_key(prefix: str, value: str) -> str:
    """Build a Streamlit-safe widget key by hashing non-alphanumeric values."""
    safe = hashlib.md5(value.encode()).hexdigest()[:12]
    return f"{prefix}_{safe}"


def _render_document_list(svc: DataService, collection_filter: str | None) -> None:
    docs = svc.list_documents(collection=collection_filter)
    if not docs:
        st.info("No documents found. Ingest some data first.")
        return

    st.caption(f"{len(docs)} document(s) found")

    for i, doc in enumerate(docs):
        sp = doc["source_path"]
        with st.expander(
            f"{sp} — {doc['chunk_count']} chunks, "
            f"{doc['image_count']} images",
            expanded=(i == 0 and len(docs) == 1),
        ):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.caption(f"**Collection:** {doc['collection']}")
                st.caption(f"**Path:** {sp}")
                if doc.get("ingested_at"):
                    st.caption(f"**Ingested:** {doc['ingested_at']}")
            with col2:
                st.metric("Chunks", doc["chunk_count"])
                st.metric("Images", doc["image_count"])

            show_chunks = st.checkbox(
                "Show Chunks",
                key=_safe_key("show_chunks", f"{i}_{sp}"),
            )
            if show_chunks:
                chunks = svc.get_chunks_for_document(
                    sp, collection=doc["collection"]
                )
                _render_chunks(chunks)

            if doc["image_count"] > 0:
                show_images = st.checkbox(
                    "Show Images",
                    key=_safe_key("show_images", f"{i}_{sp}"),
                )
                if show_images:
                    images = svc.get_images_for_document(doc["collection"])
                    _render_images(svc, images)


def _render_chunks(chunks) -> None:
    if not chunks:
        st.info("No chunks available.")
        return

    for j, chunk in enumerate(chunks):
        chunk_id = chunk.get("id", str(j))
        chunk_key = _safe_key("chunk", chunk_id)

        with st.container(border=True):
            st.caption(f"**Chunk {j + 1}** — ID: `{chunk_id}`")

            text = chunk.get("text", "")
            if len(text) > 500:
                show_full = st.checkbox(
                    "Show full text",
                    key=f"full_{chunk_key}",
                )
                st.write(text if show_full else text[:500] + "...")
            else:
                st.write(text)

            metadata = chunk.get("metadata", {})
            if metadata:
                with st.expander("Metadata", expanded=False):
                    st.json(metadata)


def _render_images(svc: DataService, images) -> None:
    import os

    for j, img in enumerate(images):
        file_path = img.get("file_path", "")
        if not file_path or not os.path.isfile(file_path):
            st.caption(f"Image {j + 1}: file not found at `{file_path}`")
            continue

        b64 = svc.get_image_base64(file_path)
        if b64:
            st.caption(
                f"**Image {j + 1}** — `{img.get('image_id', 'N/A')}` "
                f"(page {img.get('page_num', '?')})"
            )
            st.image(b64, use_container_width=True)
        else:
            st.caption(f"Image {j + 1}: could not load `{file_path}`")


def main() -> None:
    st.title("Data Browser")
    st.caption("Browse ingested documents, chunks, and images.")

    svc = DataService()

    with st.sidebar:
        st.subheader("Filters")
        collections = svc.get_collections()
        all_options = ["(all)"] + collections[:COLLECTION_OPTIONS_LIMIT]
        selected = st.selectbox("Collection", all_options)
        collection_filter = None if selected == "(all)" else selected

    _render_document_list(svc, collection_filter)


main()
