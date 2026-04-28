"""Ingestion trace page — ingestion history list with stage waterfall charts."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from observability.dashboard.services.trace_service import TraceService


def _render_trace_list(svc: TraceService) -> None:
    traces = svc.load_traces(trace_type="ingestion", limit=50)

    if not traces:
        st.info(
            "No ingestion traces found. Run an ingestion to generate trace data. "
            "Traces are stored in `logs/traces.jsonl`."
        )
        return

    st.caption(f"{len(traces)} trace(s) found")

    for i, trace in enumerate(traces):
        started = trace.get("started_at", 0)
        finished = trace.get("finished_at")
        total_ms = trace.get("total_elapsed_ms", 0)
        file_path = ""
        file_hash = ""
        stages = trace.get("stages", [])

        for s in stages:
            if s.get("stage") == "integrity":
                file_path = s.get("file_path", "")
                file_hash = s.get("file_hash", "")
                break

        display_name = file_path or trace.get("trace_id", "unknown")[:12]

        col1, col2, col3 = st.columns([3, 2, 2])
        with col1:
            st.write(f"**{display_name}**")
            if file_hash:
                st.caption(f"Hash: `{file_hash[:16]}...`")
        with col2:
            st.metric("Total Time (ms)", f"{total_ms:.1f}")
        with col3:
            chunk_count = 0
            for s in stages:
                if s.get("stage") == "pipeline_done":
                    chunk_count = s.get("chunk_count", 0)
                    break
            st.metric("Chunks", chunk_count)

        with st.expander("Stage Details", expanded=(i == 0)):
            stage_data = svc.extract_stage_times(stages)
            if stage_data:
                df = pd.DataFrame(stage_data)
                df = df.sort_values("elapsed_ms", ascending=True)

                st.subheader("Stage Time Distribution")
                st.bar_chart(
                    df.set_index("stage")["elapsed_ms"],
                    horizontal=True,
                    use_container_width=True,
                )

                st.subheader("Stage Table")
                for s in stage_data:
                    st.caption(
                        f"**{s['stage']}** — {s['elapsed_ms']:.1f} ms"
                        f" | raw: `{s['raw']}`"
                    )

            # Also show raw stage details
            with st.expander("Raw Stage Data", expanded=False):
                for s in stages:
                    filtered = {k: v for k, v in s.items() if k not in ("timestamp",)}
                    st.json(filtered)

        st.divider()


def main() -> None:
    st.title("Ingestion Traces")
    st.caption("View ingestion history, stage breakdown, and performance analysis.")

    svc = TraceService()
    _render_trace_list(svc)


main()
