"""Streamlit multi-page dashboard for Modular RAG MCP Server.

Launch with: streamlit run src/observability/dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is on sys.path so that core, ingestion, etc. are importable
_SRC = Path(__file__).resolve().parents[3]  # <repo>/src
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st


def main() -> None:
    st.set_page_config(
        page_title="Modular RAG — Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    pages = [
        st.Page("pages/overview.py", title="System Overview", icon="📋"),
        st.Page("pages/data_browser.py", title="Data Browser", icon="🔍"),
        st.Page("pages/ingestion_manager.py", title="Ingestion Manager", icon="📥"),
        st.Page("pages/ingestion_traces.py", title="Ingestion Traces", icon="⏱️"),
        st.Page("pages/query_traces.py", title="Query Traces", icon="🔎"),
        st.Page("pages/evaluation_panel.py", title="Evaluation", icon="📈"),
    ]

    nav = st.navigation(pages)
    nav.run()


if __name__ == "__main__":
    main()
