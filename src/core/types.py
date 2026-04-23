"""Core domain types shared across ingestion, retrieval, and MCP tools."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

# ---------------------------------------------------------------------------
# Image / multimodal conventions (C1)
# ---------------------------------------------------------------------------

# Document.text uses this pattern; {image_id} is the value from ImageRef["id"].
IMAGE_PLACEHOLDER_TEMPLATE = "[IMAGE: {image_id}]"


def format_image_placeholder(image_id: str) -> str:
    """Return the canonical text placeholder for an image id."""
    return IMAGE_PLACEHOLDER_TEMPLATE.format(image_id=image_id)


_PLACEHOLDER_RE = re.compile(r"\[IMAGE:\s*([^\]]+?)\s*\]")


def extract_image_ids_from_text(text: str) -> List[str]:
    """Return image ids appearing in Document/Chunk text in document order."""
    return [m.group(1).strip() for m in _PLACEHOLDER_RE.finditer(text)]


def validate_metadata_source_path(metadata: Mapping[str, Any]) -> None:
    """Ensure metadata contains the minimum required ``source_path`` field."""
    if "source_path" not in metadata:
        raise ValueError("metadata must include 'source_path'")
    sp = metadata["source_path"]
    if not isinstance(sp, str) or not sp.strip():
        raise ValueError("metadata['source_path'] must be a non-empty string")


def validate_images_metadata(images: Any) -> None:
    """
    Validate ``metadata['images']`` when present.

    Expected shape: list of dicts with id, path, text_offset, text_length;
    optional page (int), position (dict).
    """
    if images is None:
        return
    if not isinstance(images, list):
        raise ValueError("metadata['images'] must be a list when present")
    for i, item in enumerate(images):
        if not isinstance(item, Mapping):
            raise ValueError(f"metadata['images'][{i}] must be a mapping")
        for key in ("id", "path", "text_offset", "text_length"):
            if key not in item:
                raise ValueError(f"metadata['images'][{i}] missing required key '{key}'")
        if not isinstance(item["id"], str) or not item["id"]:
            raise ValueError(f"metadata['images'][{i}]['id'] must be a non-empty string")
        if not isinstance(item["path"], str) or not item["path"]:
            raise ValueError(f"metadata['images'][{i}]['path'] must be a non-empty string")
        if not isinstance(item["text_offset"], int) or item["text_offset"] < 0:
            raise ValueError(f"metadata['images'][{i}]['text_offset'] must be a non-negative int")
        if not isinstance(item["text_length"], int) or item["text_length"] < 1:
            raise ValueError(f"metadata['images'][{i}]['text_length'] must be a positive int")
        if "page" in item and item["page"] is not None and not isinstance(item["page"], int):
            raise ValueError(f"metadata['images'][{i}]['page'] must be int or omitted")
        if "position" in item and item["position"] is not None:
            if not isinstance(item["position"], Mapping):
                raise ValueError(f"metadata['images'][{i}]['position'] must be a mapping when present")


def validate_document_contract(doc: "Document", *, check_images: bool = True) -> None:
    """Validate Document metadata minimums and optional images list."""
    validate_metadata_source_path(doc.metadata)
    if check_images and "images" in doc.metadata:
        validate_images_metadata(doc.metadata["images"])


def validate_chunk_contract(chunk: "Chunk", *, check_images: bool = True) -> None:
    validate_metadata_source_path(chunk.metadata)
    if check_images and "images" in chunk.metadata:
        validate_images_metadata(chunk.metadata["images"])


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass
class Document:
    """Parsed source document (e.g. from Loader)."""

    id: str
    text: str
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "metadata": dict(self.metadata)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Document:
        md = data.get("metadata") or {}
        if not isinstance(md, Mapping):
            raise TypeError("metadata must be a mapping")
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            metadata=dict(md),
        )


@dataclass
class Chunk:
    """Logical text segment derived from a Document."""

    id: str
    text: str
    metadata: Dict[str, Any]
    start_offset: int
    end_offset: int
    source_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "metadata": dict(self.metadata),
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }
        if self.source_ref is not None:
            out["source_ref"] = self.source_ref
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Chunk:
        md = data.get("metadata") or {}
        if not isinstance(md, Mapping):
            raise TypeError("metadata must be a mapping")
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            metadata=dict(md),
            start_offset=int(data["start_offset"]),
            end_offset=int(data["end_offset"]),
            source_ref=(str(data["source_ref"]) if data.get("source_ref") is not None else None),
        )


@dataclass
class ChunkRecord:
    """Storage / retrieval carrier (vectors attached; evolves in C8–C12)."""

    id: str
    text: str
    metadata: Dict[str, Any]
    dense_vector: Optional[List[float]] = None
    sparse_vector: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "metadata": dict(self.metadata),
        }
        if self.dense_vector is not None:
            out["dense_vector"] = list(self.dense_vector)
        if self.sparse_vector is not None:
            out["sparse_vector"] = dict(self.sparse_vector)
        return out

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ChunkRecord:
        md = data.get("metadata") or {}
        if not isinstance(md, Mapping):
            raise TypeError("metadata must be a mapping")
        dv = data.get("dense_vector")
        if dv is not None:
            if not isinstance(dv, Sequence) or isinstance(dv, (str, bytes)):
                raise TypeError("dense_vector must be a sequence of numbers when present")
        sv = data.get("sparse_vector")
        if sv is not None:
            if not isinstance(sv, Mapping):
                raise TypeError("sparse_vector must be a mapping when present")
            sv = dict(sv)
        dense: Optional[List[float]] = None
        if dv is not None:
            dense = [float(x) for x in dv]
        return cls(
            id=str(data["id"]),
            text=str(data["text"]),
            metadata=dict(md),
            dense_vector=dense,
            sparse_vector=sv,
        )


def to_json(obj: Union[Document, Chunk, ChunkRecord]) -> str:
    """Serialize a core type to a stable JSON string (UTF-8, sorted keys)."""
    return json.dumps(obj.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
