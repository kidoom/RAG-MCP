"""E2E tests for scripts/ingest.py (C15)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import scripts.ingest as ingest_cli


@dataclass(frozen=True)
class _FakeVectorStoreSettings:
    collection_name: str = "kb-default"


@dataclass(frozen=True)
class _FakeSettings:
    vector_store: _FakeVectorStoreSettings = _FakeVectorStoreSettings()


@dataclass(frozen=True)
class _FakeResult:
    file_path: str
    file_hash: str
    skipped: bool
    doc_id: str
    chunk_count: int
    record_count: int
    image_count: int


class _FakePipeline:
    _seen: set[str] = set()

    def __init__(self, settings):
        self.settings = settings

    def run(self, file_path: str, *, collection: str, force: bool = False):
        key = str(Path(file_path).resolve())
        if key in self._seen and not force:
            return _FakeResult(key, "h", True, "", 0, 0, 0)
        self._seen.add(key)
        return _FakeResult(key, "h", False, "doc-1", 3, 3, 0)


@pytest.mark.e2e
def test_ingest_cli_processes_pdfs_and_skips_repeated(monkeypatch, tmp_path: Path, capsys) -> None:
    # Arrange input files.
    d = tmp_path / "docs"
    d.mkdir()
    (d / "a.pdf").write_bytes(b"pdf-a")
    (d / "b.pdf").write_bytes(b"pdf-b")
    (d / "ignore.txt").write_text("x", encoding="utf-8")

    _FakePipeline._seen.clear()
    monkeypatch.setattr(ingest_cli, "load_settings", lambda _: _FakeSettings())
    monkeypatch.setattr(ingest_cli, "IngestionPipeline", _FakePipeline)

    # First run -> processed.
    code1 = ingest_cli.main(["--path", str(d), "--collection", "kb-a"])
    out1 = capsys.readouterr().out
    assert code1 == 0
    assert "processed=2" in out1
    assert "skipped=0" in out1

    # Second run -> skipped.
    code2 = ingest_cli.main(["--path", str(d), "--collection", "kb-a"])
    out2 = capsys.readouterr().out
    assert code2 == 0
    assert "processed=0" in out2
    assert "skipped=2" in out2


@pytest.mark.e2e
def test_ingest_cli_force_reprocesses(monkeypatch, tmp_path: Path, capsys) -> None:
    f = tmp_path / "one.pdf"
    f.write_bytes(b"pdf")

    _FakePipeline._seen.clear()
    monkeypatch.setattr(ingest_cli, "load_settings", lambda _: _FakeSettings())
    monkeypatch.setattr(ingest_cli, "IngestionPipeline", _FakePipeline)

    assert ingest_cli.main(["--path", str(f)]) == 0
    _ = capsys.readouterr()
    assert ingest_cli.main(["--path", str(f), "--force"]) == 0
    out = capsys.readouterr().out
    assert "processed=1" in out
    assert "skipped=0" in out
