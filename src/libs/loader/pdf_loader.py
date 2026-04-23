"""PDF loader implementation with optional image extraction."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.core import Document, format_image_placeholder, validate_document_contract

from .base_loader import BaseLoader

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_IMAGE_ROOT = REPO_ROOT / "data" / "images"


class PdfLoader(BaseLoader):
    """Load PDF into a Document with text and optional image placeholders."""

    def __init__(
        self,
        image_root: Optional[str] = None,
        enable_image_extraction: bool = True,
        reader_factory: Optional[Callable[[str], Any]] = None,
    ):
        self.image_root = Path(image_root) if image_root else DEFAULT_IMAGE_ROOT
        self.enable_image_extraction = enable_image_extraction
        self._reader_factory = reader_factory

    def load(self, path: str, trace: Optional[Any] = None) -> Document:
        fp = Path(path)
        if not fp.is_file():
            raise FileNotFoundError(f"PDF file not found: {fp}")

        reader = self._create_reader(str(fp))
        doc_hash = self._compute_file_hash(fp)
        parts: List[str] = []
        images: List[Dict[str, Any]] = []
        cursor = 0

        for page_idx, page in enumerate(reader.pages, start=1):
            if page_idx > 1:
                parts.append("\n\n")
                cursor += 2

            page_text = self._extract_page_text(page, page_idx)
            if page_text:
                parts.append(page_text)
                cursor += len(page_text)

            try:
                page_images = self._extract_page_images(page, page_idx, doc_hash)
            except Exception as exc:  # noqa: BLE001 - degrade by design for C3
                logger.warning("Image extraction failed on page %s: %s", page_idx, exc)
                page_images = []

            for image_meta in page_images:
                if cursor > 0 and (not parts or not parts[-1].endswith("\n")):
                    parts.append("\n")
                    cursor += 1

                placeholder = format_image_placeholder(image_meta["id"])
                image_meta["text_offset"] = cursor
                image_meta["text_length"] = len(placeholder)
                parts.append(placeholder)
                cursor += len(placeholder)
                images.append(image_meta)

        full_text = "".join(parts).strip()
        metadata: Dict[str, Any] = {
            "source_path": str(fp.resolve()),
            "page_count": len(reader.pages),
        }
        if images:
            metadata["images"] = images

        document = Document(
            id=doc_hash,
            text=full_text,
            metadata=metadata,
        )
        validate_document_contract(document)
        return document

    @staticmethod
    def _compute_file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _extract_page_text(page: Any, page_num: int) -> str:
        try:
            text = page.extract_text()
        except Exception as exc:  # noqa: BLE001 - parser variance by PDF
            logger.warning("Text extraction failed on page %s: %s", page_num, exc)
            text = ""
        return (text or "").strip()

    def _extract_page_images(self, page: Any, page_num: int, doc_hash: str) -> List[Dict[str, Any]]:
        if not self.enable_image_extraction:
            return []

        images_obj = getattr(page, "images", None)
        if not images_obj:
            return []

        output_dir = self.image_root / doc_hash
        output_dir.mkdir(parents=True, exist_ok=True)
        out: List[Dict[str, Any]] = []

        for index, img in enumerate(images_obj):
            image_id = f"{doc_hash}_{page_num}_{index}"
            ext = Path(getattr(img, "name", "")).suffix or ".png"
            file_name = f"{image_id}{ext}"
            file_path = output_dir / file_name
            data = getattr(img, "data", b"")
            if not isinstance(data, (bytes, bytearray)) or not data:
                continue
            file_path.write_bytes(data)
            out.append(
                {
                    "id": image_id,
                    "path": self._to_repo_relative(file_path),
                    "page": page_num,
                    "position": {},
                }
            )
        return out

    def _create_reader(self, path: str) -> Any:
        if self._reader_factory is not None:
            return self._reader_factory(path)

        try:
            from pypdf import PdfReader  # type: ignore[import-not-found]
        except ImportError:
            try:
                from PyPDF2 import PdfReader  # type: ignore[import-not-found]
            except ImportError as exc:
                raise ImportError(
                    "PDF loader requires 'pypdf' (preferred) or 'PyPDF2'. "
                    "Install one of them to enable real PDF parsing."
                ) from exc
        return PdfReader(path)

    @staticmethod
    def _to_repo_relative(path: Path) -> str:
        try:
            return path.resolve().relative_to(REPO_ROOT).as_posix()
        except ValueError:
            return path.resolve().as_posix()
