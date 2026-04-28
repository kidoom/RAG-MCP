"""Ingestion manager page — file upload, ingest trigger, progress, and document deletion."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

import streamlit as st

from core.settings import load_settings
from core.trace.trace_collector import TraceCollector
from core.trace.trace_context import TraceContext
from ingestion.document_manager import DocumentManager
from ingestion.pipeline import IngestionPipeline
from observability.dashboard.services.data_service import DataService
from observability.logger import write_trace


def _safe_key(prefix: str, value: str) -> str:
    safe = hashlib.md5(value.encode()).hexdigest()[:12]
    return f"{prefix}_{safe}"


def _persist_trace(trace_dict) -> None:
    try:
        write_trace(trace_dict)
    except Exception:
        pass


def main() -> None:
    st.title("Ingestion Manager")
    st.caption("Upload files, trigger ingestion, manage existing documents.")

    mgr = DocumentManager()
    svc = DataService(document_manager=mgr)

    tab_upload, tab_manage = st.tabs(["Upload & Ingest", "Manage Documents"])

    with tab_upload:
        _render_upload_tab(mgr)

    with tab_manage:
        _render_manage_tab(mgr, svc)


def _render_upload_tab(mgr: DocumentManager) -> None:
    settings = load_settings()
    if settings.ingestion is None:
        st.error("Ingestion settings are not configured in settings.yaml.")
        return

    uploaded_files = st.file_uploader(
        "Choose files to ingest",
        type=["pdf", "txt", "md", "csv", "json"],
        accept_multiple_files=True,
        help="Supported formats: PDF, TXT, MD, CSV, JSON",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        default_coll = settings.vector_store.collection_name
        collection = st.text_input("Collection", value=default_coll)
    with col2:
        force = st.checkbox(
            "Force re-ingest",
            help="Re-ingest even if file hash is unchanged",
        )
    with col3:
        st.caption("")

    if not uploaded_files:
        st.info("Upload one or more files to begin.")
        return

    if st.button("Start Ingestion", type="primary", use_container_width=True):
        pipeline = IngestionPipeline(settings)

        progress_placeholder = st.empty()
        status_placeholder = st.empty()

        total_files = len(uploaded_files)
        results = []

        for idx, uploaded in enumerate(uploaded_files):
            suffix = Path(uploaded.name).suffix or ".tmp"
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix="rag_ingest_"
            ) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            status_placeholder.info(
                f"[{idx + 1}/{total_files}] Ingesting: {uploaded.name}"
            )

            progress_bar = progress_placeholder.progress(0, text="Starting...")

            # Bind progress_bar as default arg to avoid closure bug
            def on_progress(
                stage: str,
                current: int,
                total: int,
                _bar: object = progress_bar,
            ) -> None:
                pct = float(current) / float(max(total, 1))
                _bar.progress(min(pct, 1.0), text=f"Stage: {stage}")

            trace_ctx = TraceContext(trace_type="ingestion")
            collector = TraceCollector(on_collect=_persist_trace)

            try:
                result = pipeline.run(
                    file_path=tmp_path,
                    collection=collection,
                    force=force,
                    trace=trace_ctx,
                    on_progress=on_progress,
                )
                collector.collect(trace_ctx)
                results.append(result)
                if result.skipped:
                    status_placeholder.warning(
                        f"Skipped: {uploaded.name} (unchanged)"
                    )
                else:
                    status_placeholder.success(
                        f"Ingested: {uploaded.name} ({result.chunk_count} chunks, "
                        f"{result.image_count} images)"
                    )
            except Exception as exc:
                collector.collect(trace_ctx)
                status_placeholder.error(f"Failed: {uploaded.name} — {exc}")
                results.append(None)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        progress_placeholder.empty()

        succeeded = sum(1 for r in results if r is not None and not r.skipped)
        skipped = sum(1 for r in results if r is not None and r.skipped)
        failed = sum(1 for r in results if r is None)
        st.success(
            f"Done: {succeeded} succeeded, {skipped} skipped, {failed} failed"
        )

        if succeeded > 0:
            st.rerun()


def _render_manage_tab(mgr: DocumentManager, svc: DataService) -> None:
    st.subheader("Existing Documents")

    # Show toast from previous delete action
    if st.session_state.get("delete_success_msg"):
        st.success(st.session_state.pop("delete_success_msg"))

    try:
        docs = svc.list_documents()
    except Exception as exc:
        st.error(f"Failed to list documents: {exc}")
        return

    if not docs:
        st.info("No documents have been ingested yet.")
        return

    st.caption(f"{len(docs)} document(s) found")

    for i, doc in enumerate(docs):
        sp = doc["source_path"]
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
        with col1:
            st.write(f"**{sp}**")
            st.caption(f"Collection: {doc['collection']}")
        with col2:
            st.metric("Chunks", doc["chunk_count"])
        with col3:
            st.metric("Images", doc["image_count"])
        with col4:
            delete_key = _safe_key("delete", f"{i}_{sp}")
            if st.button("Delete", key=delete_key, type="secondary"):
                with st.spinner(f"Deleting {sp}..."):
                    result = mgr.delete_document(
                        sp, collection=doc["collection"]
                    )
                if result.success:
                    st.session_state["delete_success_msg"] = f"Deleted: {sp}"
                    st.rerun()
                else:
                    st.error(f"Delete failed: {'; '.join(result.errors)}")
        st.divider()


main()
