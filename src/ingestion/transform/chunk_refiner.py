"""Rule-based chunk cleanup with optional LLM rewrite (graceful fallback)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from libs.llm.base_llm import BaseLLM, LLMSettings as LibLLMSettings
from libs.llm.llm_factory import LLMFactory

from .base_transform import BaseTransform

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROMPT_PATH = _REPO_ROOT / "config" / "prompts" / "chunk_refinement.txt"

# Fallback if prompt file is missing in test / minimal installs.
_BUILTIN_PROMPT = (
    "Refine the following text chunk for retrieval. "
    "Remove noise (headers/footers, redundant whitespace, HTML comments). "
    "Preserve code fences and their inner content. "
    "Return only the refined plain text, no preamble.\n\n"
    "{text}"
)

_CODE_BLOCK_RE = re.compile(r"(```[\w]*\n.*?```)", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_PAGE_OF_RE = re.compile(r"(?im)^\s*page\s+\d+\s+of\s+\d+\s*$")
_HRULE_LINE_RE = re.compile(r"^\s*[-_*]{3,}\s*$", re.MULTILINE)


def _lib_llm_settings_from_core(settings: Settings) -> LibLLMSettings:
    llm = settings.llm
    return LibLLMSettings(
        provider=llm.provider,
        model=llm.model,
        api_key=llm.api_key or None,
        base_url=llm.base_url or None,
        azure_endpoint=llm.azure_endpoint or None,
        deployment_name=llm.deployment_name or None,
        api_version=llm.api_version or None,
        temperature=float(llm.temperature),
        max_tokens=int(llm.max_tokens),
    )


class ChunkRefiner(BaseTransform):
    """Apply rule cleanup, then optional LLM polish; failures fall back to rules."""

    def __init__(
        self,
        settings: Settings,
        llm: Optional[BaseLLM] = None,
        prompt_path: Optional[str] = None,
    ):
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' for ChunkRefiner")

        self._settings = settings
        cr = settings.ingestion.chunk_refiner
        self._use_llm = bool(cr and cr.use_llm)

        self._prompt_path = Path(prompt_path) if prompt_path else _DEFAULT_PROMPT_PATH
        self._prompt_template = self._load_prompt_template(self._prompt_path)

        if self._use_llm and llm is None:
            self._llm = LLMFactory.create_llm(_lib_llm_settings_from_core(settings))
        else:
            self._llm = llm if self._use_llm else None

    @staticmethod
    def _load_prompt_template(path: Path) -> str:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Chunk refinement prompt missing at %s; using builtin", path)
            return _BUILTIN_PROMPT
        text = raw.strip()
        if "{text}" not in text:
            text = text.rstrip() + "\n\n{text}"
        return text

    def transform(
        self, chunks: List[Chunk], trace: Optional[TraceContext] = None
    ) -> List[Chunk]:
        if trace is not None:
            trace.record_stage("chunk_refiner", chunk_count=len(chunks), use_llm=self._use_llm)

        out: List[Chunk] = []
        for chunk in chunks:
            try:
                out.append(self._refine_one(chunk, trace))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Chunk refinement failed for %s", chunk.id)
                md = dict(chunk.metadata)
                md["refined_by"] = "rule"
                md["chunk_refinement_error"] = str(exc)
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

    def _refine_one(self, chunk: Chunk, trace: Optional[TraceContext]) -> Chunk:
        if not chunk.text.strip():
            md = dict(chunk.metadata)
            md.setdefault("refined_by", "rule")
            return Chunk(
                id=chunk.id,
                text=chunk.text,
                metadata=md,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                source_ref=chunk.source_ref,
            )

        rule_text = self._rule_based_refine(chunk.text)
        if not rule_text.strip():
            rule_text = chunk.text

        final_text = rule_text
        refined_by = "rule"
        fallback_reason: Optional[str] = None

        if self._use_llm and self._llm is not None:
            llm_text = self._llm_refine(rule_text, trace)
            if llm_text is not None and llm_text.strip():
                final_text = llm_text.strip()
                refined_by = "llm"
            else:
                fallback_reason = "llm_failed_or_empty"

        md = dict(chunk.metadata)
        md["refined_by"] = refined_by
        if fallback_reason:
            md["refinement_fallback_reason"] = fallback_reason

        return Chunk(
            id=chunk.id,
            text=final_text,
            metadata=md,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            source_ref=chunk.source_ref,
        )

    def _rule_based_refine(self, text: str) -> str:
        """Strip noise outside fenced code blocks; keep ``` bodies intact."""
        parts: List[str] = []
        idx = 0
        for m in  _CODE_BLOCK_RE.finditer(text):
            parts.append(self._refine_plain_segment(text[idx : m.start()]))
            parts.append(m.group(1))
            idx = m.end()
        parts.append(self._refine_plain_segment(text[idx:]))
        return "".join(parts).strip()

    @staticmethod
    def _refine_plain_segment(segment: str) -> str:
        s = segment.replace("\r\n", "\n")
        s = _HTML_COMMENT_RE.sub("", s)
        s = _PAGE_OF_RE.sub("", s)
        s = _HRULE_LINE_RE.sub("", s)
        s = re.sub(r"\n{3,}", "\n\n", s)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r"\n[ \t]+", "\n", s)
        return s

    def _llm_refine(self, text: str, trace: Optional[TraceContext]) -> Optional[str]:
        prompt = self._prompt_template.format(text=text)
        assert self._llm is not None
        try:
            out = self._llm.generate(prompt)
        except Exception as exc:  # noqa: BLE001
            if trace is not None:
                trace.record_stage("chunk_refiner_llm_error", error=str(exc))
            logger.warning("LLM refinement failed: %s", exc)
            return None
        if not isinstance(out, str) or not out.strip():
            return None
        if trace is not None:
            trace.record_stage("chunk_refiner_llm_ok", output_chars=len(out))
        return out.strip()
