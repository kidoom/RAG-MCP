#!/usr/bin/env python
"""Run evaluation against golden test set.

Usage:
    python scripts/evaluate.py
    python scripts/evaluate.py --test-set tests/fixtures/golden_test_set.json
"""

from __future__ import annotations

import os
import sys
from argparse import ArgumentParser

# Ensure src/ is on sys.path
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


def main() -> None:
    parser = ArgumentParser(description="Run RAG evaluation against golden test set")
    parser.add_argument(
        "--test-set",
        type=str,
        default="tests/fixtures/golden_test_set.json",
        help="Path to golden test set JSON file",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="custom",
        help="Evaluator provider (custom, ragas)",
    )
    args = parser.parse_args()

    from observability.evaluation.eval_runner import EvalRunner

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_set_path = os.path.join(repo_root, args.test_set)

    if not os.path.isfile(test_set_path):
        print(f"Error: Test set not found at {test_set_path}", file=sys.stderr)
        sys.exit(1)

    runner = EvalRunner()

    print(f"Running evaluation with provider='{args.provider}'...")
    print(f"Test set: {test_set_path}")
    print()

    try:
        report = runner.run(test_set_path)
        print(report.summary())
    except Exception as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
