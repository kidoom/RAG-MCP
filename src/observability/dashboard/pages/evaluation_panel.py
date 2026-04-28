"""Evaluation panel page — run evaluation, view metrics, and compare results (H4)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from core.settings import REPO_ROOT
from libs.evaluator.evaluator_factory import EvaluatorFactory
from libs.evaluator.base_evaluator import EvaluatorSettings

DEFAULT_TEST_SET = REPO_ROOT / "tests" / "fixtures" / "golden_test_set.json"


def _load_test_set(path: str) -> int:
    """Count test cases in a golden test set file."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return len(data.get("test_cases", []))
    except Exception:
        return 0


def _load_report(json_path: str) -> dict | None:
    try:
        with open(json_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def main() -> None:
    st.title("Evaluation Panel")
    st.caption("Run evaluation against golden test sets and review metrics.")

    providers = EvaluatorFactory.list_providers()

    col1, col2, col3 = st.columns(3)
    with col1:
        provider = st.selectbox("Evaluator Provider", providers, index=0)
    with col2:
        test_set_default = str(DEFAULT_TEST_SET) if DEFAULT_TEST_SET.exists() else ""
        test_set_path = st.text_input(
            "Golden Test Set Path",
            value=test_set_default,
            help="Path to JSON file with test_cases",
        )
    with col3:
        top_k = st.number_input("Top-K", min_value=1, value=10, max_value=100)

    if test_set_path:
        count = _load_test_set(test_set_path)
        st.caption(f"Test set contains **{count}** queries.")

    if st.button("Run Evaluation", type="primary", use_container_width=True):
        if not test_set_path or not os.path.isfile(test_set_path):
            st.error(f"Test set not found: `{test_set_path}`")
            return

        with st.spinner("Running evaluation..."):
            try:
                from observability.evaluation.eval_runner import EvalRunner

                eval_settings = EvaluatorSettings(provider=provider, top_k=top_k)
                evaluator = EvaluatorFactory.create(eval_settings)

                runner = EvalRunner(evaluator=evaluator)
                report = runner.run(test_set_path)

                st.success(f"Evaluation complete — {report.total_queries} queries")

                # Aggregate metrics
                st.subheader("Aggregate Metrics")
                metric_cols = st.columns(4)
                metric_keys = sorted(report.metrics.keys())
                for i, k in enumerate(metric_keys):
                    with metric_cols[i % 4]:
                        st.metric(k, f"{report.metrics[k]:.4f}")

                # Per-query details
                st.subheader("Per-Query Results")
                if report.per_query:
                    rows = []
                    for qr in report.per_query:
                        row = {
                            "Query": str(qr.get("query", ""))[:80],
                            "Retrieved": len(qr.get("retrieved_ids", [])),
                            "Expected": len(qr.get("expected_ids", [])),
                        }
                        row.update(qr.get("metrics", {}))
                        rows.append(row)

                    if rows:
                        st.dataframe(
                            pd.DataFrame(rows),
                            use_container_width=True,
                            hide_index=True,
                        )

                # Detailed breakdown
                with st.expander("Full Report JSON", expanded=False):
                    st.json(report.to_dict())

            except Exception as exc:
                st.error(f"Evaluation failed: {exc}")

    st.divider()
    st.subheader("Historical Reports")

    reports_dir = REPO_ROOT / "logs" / "eval_reports"
    if reports_dir.exists():
        report_files = sorted(
            reports_dir.glob("*.json"),
            key=os.path.getmtime,
            reverse=True,
        )[:5]
        if report_files:
            for rf in report_files:
                report = _load_report(str(rf))
                if report:
                    with st.expander(
                        f"{rf.name} — {report.get('total_queries', '?')} queries"
                    ):
                        st.json(report, expanded=False)
        else:
            st.caption("No historical reports found.")
    else:
        st.caption(
            "No historical reports yet. Run an evaluation to generate reports "
            f"in `{reports_dir}`."
        )


main()
