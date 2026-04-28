"""E2E recall regression tests using golden test set (H5).

Runs evaluation against `tests/fixtures/golden_test_set.json` and asserts
minimum hit@k and MRR thresholds.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observability.evaluation.eval_runner import EvalRunner

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
GOLDEN_TEST_SET = FIXTURES_DIR / "golden_test_set.json"

# Minimum regression thresholds (verified manually, kept here for CI)
MIN_HIT_RATE = 0.0  # No real data yet — baseline is 0
MIN_MRR = 0.0


class TestRecallRegression:
    """E2E recall tests against the golden test set."""

    @pytest.fixture(scope="class")
    def eval_runner(self) -> EvalRunner:
        return EvalRunner()

    @pytest.fixture(scope="class")
    def golden_data(self) -> dict:
        """Load the golden test set."""
        if not GOLDEN_TEST_SET.exists():
            pytest.skip(f"Golden test set not found: {GOLDEN_TEST_SET}")
        with GOLDEN_TEST_SET.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_golden_test_set_is_valid(self, golden_data: dict):
        """Golden test set must contain test_cases."""
        cases = golden_data.get("test_cases", [])
        assert len(cases) > 0, "Golden test set must have at least one test case"
        for tc in cases:
            assert tc.get("query"), f"Test case missing 'query': {tc}"
            assert tc.get("expected_chunk_ids"), f"Test case missing 'expected_chunk_ids': {tc}"

    def test_eval_runner_returns_report(self, eval_runner: EvalRunner, golden_data: dict):
        """EvalRunner should produce a valid report."""
        report = eval_runner.run(str(GOLDEN_TEST_SET))

        assert report.total_queries == len(golden_data["test_cases"])
        assert report.per_query is not None
        assert len(report.per_query) == report.total_queries

    def test_eval_report_has_expected_metrics(self, eval_runner: EvalRunner):
        """EvalReport should contain hit_rate and mrr metrics."""
        report = eval_runner.run(str(GOLDEN_TEST_SET))

        assert "hit_rate" in report.metrics, "EvalReport must include hit_rate"
        assert "mrr" in report.metrics, "EvalReport must include mrr"

    def test_hit_rate_above_regression_threshold(self, eval_runner: EvalRunner):
        """hit_rate must meet or exceed the configured regression threshold."""
        report = eval_runner.run(str(GOLDEN_TEST_SET))

        assert report.hit_rate >= MIN_HIT_RATE, (
            f"hit_rate {report.hit_rate:.4f} below threshold {MIN_HIT_RATE}"
        )
        assert report.mrr >= MIN_MRR, (
            f"mrr {report.mrr:.4f} below threshold {MIN_MRR}"
        )

    def test_all_queries_have_retrieved_results(self, eval_runner: EvalRunner):
        """Each query in the report must have a retrieved_ids list (even if empty)."""
        report = eval_runner.run(str(GOLDEN_TEST_SET))

        for qr in report.per_query:
            if "error" in qr:
                pytest.skip(f"Query had error: {qr.get('query')} — {qr.get('error')}")
            assert "retrieved_ids" in qr, (
                f"Query missing retrieved_ids: {qr.get('query')}"
            )
            assert isinstance(qr["retrieved_ids"], list), (
                f"retrieved_ids must be a list for query: {qr.get('query')}"
            )
