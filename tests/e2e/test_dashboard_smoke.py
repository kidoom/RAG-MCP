"""E2E Dashboard smoke tests using Streamlit AppTest (I2).

Verifies all 6 dashboard pages render without Python exceptions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve()
_SRC_DIR = _THIS_DIR.parents[2] / "src"

if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

PAGES = [
    ("overview", "observability/dashboard/pages/overview.py"),
    ("data_browser", "observability/dashboard/pages/data_browser.py"),
    ("ingestion_manager", "observability/dashboard/pages/ingestion_manager.py"),
    ("ingestion_traces", "observability/dashboard/pages/ingestion_traces.py"),
    ("query_traces", "observability/dashboard/pages/query_traces.py"),
    ("evaluation_panel", "observability/dashboard/pages/evaluation_panel.py"),
]


@pytest.mark.e2e
class TestDashboardSmoke:
    """Smoke test: all 6 dashboard pages render without exceptions."""

    def test_overview_renders(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(
            str(_SRC_DIR / "observability/dashboard/pages/overview.py"),
            default_timeout=30,
        )
        at.run()
        assert len(at.exception) == 0, f"overview exceptions: {at.exception}"
        assert len(at.error) == 0, f"overview errors: {at.error}"

    def test_data_browser_renders(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(
            str(_SRC_DIR / "observability/dashboard/pages/data_browser.py"),
            default_timeout=30,
        )
        at.run()
        assert len(at.exception) == 0, f"data_browser exceptions: {at.exception}"
        assert len(at.error) == 0, f"data_browser errors: {at.error}"

    def test_ingestion_manager_renders(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(
            str(_SRC_DIR / "observability/dashboard/pages/ingestion_manager.py"),
            default_timeout=30,
        )
        at.run()
        assert len(at.exception) == 0, f"ingestion_manager exceptions: {at.exception}"
        assert len(at.error) == 0, f"ingestion_manager errors: {at.error}"

    def test_ingestion_traces_renders(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(
            str(_SRC_DIR / "observability/dashboard/pages/ingestion_traces.py"),
            default_timeout=30,
        )
        at.run()
        assert len(at.exception) == 0, f"ingestion_traces exceptions: {at.exception}"
        assert len(at.error) == 0, f"ingestion_traces errors: {at.error}"

    def test_query_traces_renders(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(
            str(_SRC_DIR / "observability/dashboard/pages/query_traces.py"),
            default_timeout=30,
        )
        at.run()
        assert len(at.exception) == 0, f"query_traces exceptions: {at.exception}"
        assert len(at.error) == 0, f"query_traces errors: {at.error}"

    def test_evaluation_panel_renders(self):
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(
            str(_SRC_DIR / "observability/dashboard/pages/evaluation_panel.py"),
            default_timeout=30,
        )
        at.run()
        assert len(at.exception) == 0, f"evaluation_panel exceptions: {at.exception}"
        assert len(at.error) == 0, f"evaluation_panel errors: {at.error}"
