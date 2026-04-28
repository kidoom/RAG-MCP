"""Data access service for Dashboard UI — wraps ChromaStore and ImageStorage reads."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ingestion.document_manager import DocumentManager
from ingestion.storage.image_storage import ImageStorage


class DataService:
    """Encapsulates ChromaStore/ImageStorage reads for the dashboard UI."""

    def __init__(
        self,
        document_manager: Optional[DocumentManager] = None,
        image_storage: Optional[ImageStorage] = None,
    ) -> None:
        self._doc_mgr = document_manager or DocumentManager()
        self._images = image_storage or ImageStorage()

    def list_documents(
        self, collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return document summary list for display."""
        docs = self._doc_mgr.list_documents(collection=collection)
        return [
            {
                "source_path": d.source_path,
                "collection": d.collection,
                "chunk_count": d.chunk_count,
                "image_count": d.image_count,
                "ingested_at": d.ingested_at,
            }
            for d in docs
        ]

    def get_chunks_for_document(
        self, source_path: str, collection: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return all chunks for a given document source_path."""
        detail = self._doc_mgr.get_document_detail(source_path, collection=collection)
        if detail is None:
            return []
        return detail.chunks

    def get_images_for_document(
        self, collection: str, doc_hash: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return image records for a document."""
        return self._images.list_images(collection, doc_hash=doc_hash)

    def get_image_base64(self, image_path: str) -> Optional[str]:
        """Read an image file and return base64-encoded string for display."""
        import base64
        from pathlib import Path

        p = Path(image_path)
        if not p.exists():
            return None
        try:
            data = p.read_bytes()
            ext = p.suffix.lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime = mime_map.get(ext, "image/png")
            b64 = base64.b64encode(data).decode("ascii")
            return f"data:{mime};base64,{b64}"
        except Exception:
            return None

    def get_collections(self) -> List[str]:
        """List available collections."""
        try:
            return self._doc_mgr._chroma.get_all_collections()
        except Exception:
            return []
