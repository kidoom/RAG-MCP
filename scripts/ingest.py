#!/usr/bin/env python3
"""CLI entrypoint for offline ingestion (C15)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.settings import SettingsError, load_settings  # noqa: E402
from ingestion.pipeline import IngestionPipeline, IngestionPipelineError  # noqa: E402


def _iter_pdf_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() == ".pdf":
            yield path
        return
    if not path.is_dir():
        return
    for file_path in sorted(path.rglob("*.pdf")):
        if file_path.is_file():
            yield file_path


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline ingestion pipeline")
    parser.add_argument(
        "--path",
        required=True,
        help="Input PDF file or directory containing PDF files",
    )
    parser.add_argument(
        "--collection",
        default="",
        help="Target collection name (default: settings.vector_store.collection_name)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if file hash is already marked successful",
    )
    parser.add_argument(
        "--settings",
        default="",
        help="Optional custom settings.yaml path",
    )
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    target = Path(args.path).resolve()

    if not target.exists():
        print(f"[ingest] path not found: {target}", file=sys.stderr)
        return 1

    try:
        settings = load_settings(args.settings or None)
    except SettingsError as exc:
        print(f"[ingest] settings error: {exc}", file=sys.stderr)
        return 1

    pipeline = IngestionPipeline(settings)
    collection = args.collection.strip() or settings.vector_store.collection_name
    files = list(_iter_pdf_files(target))
    if not files:
        print(f"[ingest] no PDF files found under: {target}")
        return 0

    processed = 0
    skipped = 0
    failed = 0

    for file_path in files:
        try:
            result = pipeline.run(
                str(file_path),
                collection=collection,
                force=args.force,
            )
        except IngestionPipelineError as exc:
            failed += 1
            print(f"[ingest] FAILED {file_path}: {exc}", file=sys.stderr)
            continue
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[ingest] FAILED {file_path}: {exc}", file=sys.stderr)
            continue

        if result.skipped:
            skipped += 1
            print(f"[ingest] SKIP {file_path}")
        else:
            processed += 1
            print(
                "[ingest] OK "
                f"{file_path} chunks={result.chunk_count} "
                f"records={result.record_count} images={result.image_count}"
            )

    print(
        "[ingest] summary "
        f"total={len(files)} processed={processed} skipped={skipped} failed={failed}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
