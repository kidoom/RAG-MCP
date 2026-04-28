"""Assemble MCP multimodal content blocks from retrieval results."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List

from core.types import RetrievalResult
from ingestion.storage import ImageStorage


class MultimodalAssembler:
    """Append image content when retrieval chunks reference stored images."""

    def __init__(self, image_storage: ImageStorage | None = None) -> None:
        self._image_storage = image_storage or ImageStorage()

    def assemble(self, retrieval_results: List[RetrievalResult]) -> List[Dict[str, Any]]:
        content: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for item in retrieval_results:
            metadata = item.metadata or {}
            image_ids = self._extract_image_ids(metadata)
            for image_id in image_ids:
                if image_id in seen:
                    continue
                seen.add(image_id)

                image_path = self._image_storage.get_image_path(image_id)
                if not image_path:
                    continue
                path_obj = Path(image_path)
                if not path_obj.exists():
                    continue

                mime_type = self._guess_mime_type(path_obj.suffix.lower())
                encoded = base64.b64encode(path_obj.read_bytes()).decode("ascii")
                content.append(
                    {
                        "type": "image",
                        "mimeType": mime_type,
                        "data": encoded,
                    }
                )
        return content

    @staticmethod
    def _extract_image_ids(metadata: Dict[str, Any]) -> List[str]:
        refs: List[str] = []
        image_refs = metadata.get("image_refs")
        if isinstance(image_refs, list):
            refs.extend(str(item).strip() for item in image_refs if str(item).strip())

        images = metadata.get("images")
        if isinstance(images, list):
            for item in images:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    image_id = item["id"].strip()
                    if image_id:
                        refs.append(image_id)
        return refs

    @staticmethod
    def _guess_mime_type(suffix: str) -> str:
        if suffix in (".jpg", ".jpeg"):
            return "image/jpeg"
        if suffix == ".gif":
            return "image/gif"
        if suffix == ".webp":
            return "image/webp"
        return "image/png"
