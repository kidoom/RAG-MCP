"""Image captioning transform with optional Vision LLM and graceful fallback."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from libs.llm.base_vision_llm import BaseVisionLLM
from libs.llm.base_vision_llm import VisionLLMSettings as LibVisionLLMSettings
from libs.llm.llm_factory import LLMFactory

from .base_transform import BaseTransform

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROMPT_PATH = _REPO_ROOT / "config" / "prompts" / "image_captioning.txt"
_BUILTIN_PROMPT = (
    "You are generating retrieval-friendly image captions.\n"
    "Describe the image concisely and focus on entities, actions, and readable text.\n"
    "Image id: {image_id}\n"
    "Nearby text context:\n{context}"
)


def _lib_vision_settings_from_core(settings: Settings) -> LibVisionLLMSettings:
    v = settings.vision_llm
    return LibVisionLLMSettings(
        provider=v.provider,
        model=v.model,
        api_key=v.api_key or None,
        base_url=v.base_url or None,
        azure_endpoint=v.azure_endpoint or None,
        deployment_name=v.deployment_name or None,
        api_version=v.api_version or None,
        max_image_size=int(v.max_image_size),
        enabled=bool(v.enabled),
    )


class ImageCaptioner(BaseTransform):
    """Generate image captions into chunk metadata; never block ingestion on failures."""

    def __init__(
        self,
        settings: Settings,
        vision_llm: Optional[BaseVisionLLM] = None,
        prompt_path: Optional[str] = None,
    ):
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' for ImageCaptioner")

        self._settings = settings
        ic = settings.ingestion.image_captioner
        self._use_vision_llm = bool(
            settings.vision_llm.enabled and ic and ic.use_vision_llm
        )
        self._prompt_path = Path(prompt_path) if prompt_path else _DEFAULT_PROMPT_PATH
        self._prompt_template = self._load_prompt_template(self._prompt_path)

        if self._use_vision_llm and vision_llm is None:
            self._vision_llm = LLMFactory.create_vision_llm(
                _lib_vision_settings_from_core(settings)
            )
        else:
            self._vision_llm = vision_llm if self._use_vision_llm else None

    @staticmethod
    def _load_prompt_template(path: Path) -> str:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Image caption prompt missing at %s; using builtin", path)
            return _BUILTIN_PROMPT
        text = raw.strip()
        if "{context}" not in text:
            text = text.rstrip() + "\n\n{context}"
        if "{image_id}" not in text:
            text = "Image id: {image_id}\n" + text
        return text

    def transform(
        self, chunks: List[Chunk], trace: Optional[TraceContext] = None
    ) -> List[Chunk]:
        if trace is not None:
            trace.record_stage(
                "image_captioner",
                chunk_count=len(chunks),
                use_vision_llm=self._use_vision_llm,
            )

        out: List[Chunk] = []
        for chunk in chunks:
            try:
                out.append(self._caption_one(chunk, trace))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Image captioning failed for %s", chunk.id)
                md = dict(chunk.metadata)
                if self._has_images(chunk):
                    md["has_unprocessed_images"] = True
                    md["image_caption_error"] = str(exc)
                out.append(
                    Chunk(
                        id=chunk.id,
                        text=chunk.text,
                        metadata=md,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        source_ref=chunk.source_ref,
                    )
                )
        return out

    @staticmethod
    def _has_images(chunk: Chunk) -> bool:
        refs = chunk.metadata.get("image_refs")
        return isinstance(refs, list) and len(refs) > 0

    @staticmethod
    def _collect_image_paths(metadata: Dict[str, Any]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for item in metadata.get("images", []):
            if isinstance(item, dict):
                iid = item.get("id")
                path = item.get("path")
                if isinstance(iid, str) and iid and isinstance(path, str) and path:
                    out[iid] = path
        return out

    def _caption_one(self, chunk: Chunk, trace: Optional[TraceContext]) -> Chunk:
        image_refs = chunk.metadata.get("image_refs")
        if not isinstance(image_refs, list) or not image_refs:
            return chunk

        md = dict(chunk.metadata)
        if not self._use_vision_llm or self._vision_llm is None:
            md["has_unprocessed_images"] = True
            return Chunk(
                id=chunk.id,
                text=chunk.text,
                metadata=md,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                source_ref=chunk.source_ref,
            )

        image_paths = self._collect_image_paths(md)
        captions: Dict[str, str] = {}
        unprocessed: List[str] = []

        for image_id in image_refs:
            if not isinstance(image_id, str) or not image_id:
                continue
            path = image_paths.get(image_id)
            if not path:
                unprocessed.append(image_id)
                continue
            prompt = self._prompt_template.format(context=chunk.text, image_id=image_id)
            try:
                caption = self._vision_llm.describe_image(path, prompt=prompt)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vision LLM failed on image %s: %s", image_id, exc)
                unprocessed.append(image_id)
                if trace is not None:
                    trace.record_stage(
                        "image_captioner_llm_error",
                        chunk_id=chunk.id,
                        image_id=image_id,
                    )
                continue
            if isinstance(caption, str) and caption.strip():
                captions[image_id] = caption.strip()
            else:
                unprocessed.append(image_id)

        if captions:
            existing = md.get("image_captions")
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(captions)
            md["image_captions"] = merged

        if unprocessed:
            md["has_unprocessed_images"] = True
            md["unprocessed_image_refs"] = unprocessed
        elif captions:
            md.pop("has_unprocessed_images", None)

        if trace is not None and captions:
            trace.record_stage(
                "image_captioner_llm_ok",
                chunk_id=chunk.id,
                captioned_count=len(captions),
            )

        return Chunk(
            id=chunk.id,
            text=chunk.text,
            metadata=md,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            source_ref=chunk.source_ref,
        )
