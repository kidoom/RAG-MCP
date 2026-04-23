from __future__ import annotations

from pathlib import Path

import pytest

from src.core import IMAGE_PLACEHOLDER_TEMPLATE
from src.libs.loader import BaseLoader, PdfLoader


class _FakePage:
    def __init__(self, text: str = "", images=None):
        self._text = text
        self.images = images or []

    def extract_text(self):
        return self._text


class _FakeReader:
    def __init__(self, pages):
        self.pages = pages


def test_base_loader_is_abstract():
    with pytest.raises(TypeError):
        BaseLoader()  # type: ignore[abstract]


def test_pdf_loader_load_minimal_pdf(tmp_path: Path):
    pdf_path = tmp_path / "simple.pdf"
    pdf_path.write_bytes(b"%PDF-fake")

    loader = PdfLoader(
        image_root=str(tmp_path / "images"),
        reader_factory=lambda _: _FakeReader([_FakePage("hello page")]),
    )
    doc = loader.load(str(pdf_path))

    assert doc.id
    assert doc.metadata["source_path"].endswith("simple.pdf")
    assert "page_count" in doc.metadata
    assert doc.metadata["page_count"] == 1
    assert "images" not in doc.metadata or doc.metadata["images"] == []


def test_pdf_loader_missing_file_raises(tmp_path: Path):
    loader = PdfLoader(image_root=str(tmp_path / "images"))
    with pytest.raises(FileNotFoundError):
        loader.load(str(tmp_path / "missing.pdf"))


def test_pdf_loader_inserts_image_placeholders_and_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pdf_path = tmp_path / "with_images.pdf"
    pdf_path.write_bytes(b"%PDF-fake-with-images")

    loader = PdfLoader(
        image_root=str(tmp_path / "images"),
        reader_factory=lambda _: _FakeReader([_FakePage("page text")]),
    )
    fake_id = "docx_1_0"

    def _fake_extract_images(page, page_num: int, doc_hash: str):
        return [
            {
                "id": fake_id,
                "path": f"data/images/{doc_hash}/{fake_id}.png",
                "page": page_num,
                "position": {"x": 1},
            }
        ]

    monkeypatch.setattr(loader, "_extract_page_images", _fake_extract_images)
    doc = loader.load(str(pdf_path))

    placeholder = IMAGE_PLACEHOLDER_TEMPLATE.format(image_id=fake_id)
    assert placeholder in doc.text
    assert "images" in doc.metadata
    assert len(doc.metadata["images"]) == 1
    img = doc.metadata["images"][0]
    assert img["id"] == fake_id
    assert img["text_length"] == len(placeholder)
    assert doc.text[img["text_offset"] : img["text_offset"] + img["text_length"]] == placeholder


def test_pdf_loader_image_extract_error_degrades_gracefully(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pdf_path = tmp_path / "degrade.pdf"
    pdf_path.write_bytes(b"%PDF-fake-degrade")

    loader = PdfLoader(
        image_root=str(tmp_path / "images"),
        reader_factory=lambda _: _FakeReader([_FakePage("base text")]),
    )

    def _boom(page, page_num: int, doc_hash: str):
        raise RuntimeError("image parse failed")

    monkeypatch.setattr(loader, "_extract_page_images", _boom)
    doc = loader.load(str(pdf_path))

    assert doc.metadata["source_path"].endswith("degrade.pdf")
    assert "images" not in doc.metadata


def test_pdf_loader_requires_pdf_dependency_when_no_reader_factory(tmp_path: Path):
    pdf_path = tmp_path / "dep.pdf"
    pdf_path.write_bytes(b"%PDF-fake-dependency")

    loader = PdfLoader(image_root=str(tmp_path / "images"))
    with pytest.raises(ImportError, match="pypdf"):
        loader.load(str(pdf_path))
