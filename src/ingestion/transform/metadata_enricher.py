"""Rule-based metadata enrichment with optional LLM rewrite (graceful fallback)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from libs.llm.base_llm import BaseLLM, LLMSettings as LibLLMSettings
from libs.llm.llm_factory import LLMFactory

from .base_transform import BaseTransform

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PROMPT_PATH = _REPO_ROOT / "config" / "prompts" / "metadata_enrichment.txt"

_BUILTIN_PROMPT = (
    "Given the following text chunk, return JSON only with keys "
    '"title", "summary", "tags" (tags: list of short lowercase strings).\n\n{text}'
)

_TAG_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "have",
        "has",
        "are",
        "was",
        "were",
        "been",
        "will",
        "can",
        "not",
        "but",
        "its",
        "our",
        "your",
        "they",
        "them",
        "into",
        "also",
        "such",
        "than",
        "then",
        "when",
        "what",
        "which",
        "where",
        "while",
        "about",
        "after",
        "before",
        "between",
        "each",
        "more",
        "most",
        "some",
        "very",
    }
)


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


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if not s.startswith("```"):
        return s
    lines = s.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _rule_title_summary_tags(text: str) -> Tuple[str, str, List[str]]:
    flat = text.replace("\r\n", "\n").strip()
    if not flat:
        return "Empty chunk", "No text content.", ["empty"]

    first_line = flat.split("\n", 1)[0].strip()
    title = (first_line[:120] + ("…" if len(first_line) > 120 else "")).strip() or "Untitled"

    summary_body = re.sub(r"\s+", " ", flat)
    if len(summary_body) > 400:
        cut = summary_body[:400]
        sp = cut.rfind(" ")
        summary = (cut[:sp] if sp > 200 else cut) + "…"
    else:
        summary = summary_body

    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", flat.lower())
    tags: List[str] = []
    seen = set()
    for w in words:
        if w in _TAG_STOP or w in seen:
            continue
        seen.add(w)
        tags.append(w)
        if len(tags) >= 6:
            break
    if not tags:
        tags = ["document"]

    return title, summary, tags


def _normalize_parsed(obj: Any) -> Optional[Tuple[str, str, List[str]]]:
    if not isinstance(obj, dict):
        return None
    title = obj.get("title")
    summary = obj.get("summary")
    tags_raw = obj.get("tags")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(summary, str) or not summary.strip():
        return None
    if not isinstance(tags_raw, list) or not tags_raw:
        return None
    tags: List[str] = []
    for t in tags_raw:
        if isinstance(t, str) and t.strip():
            tags.append(t.strip().lower())
    if not tags:
        return None
    return title.strip(), summary.strip(), tags


def _parse_llm_json(raw: str) -> Optional[Tuple[str, str, List[str]]]:
    try:
        data = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return None
    return _normalize_parsed(data)


class MetadataEnricher(BaseTransform):
    """Add title / summary / tags to chunk metadata; LLM optional with rule fallback."""

    def __init__(
        self,
        settings: Settings,
        llm: Optional[BaseLLM] = None,
        prompt_path: Optional[str] = None,
    ):
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' for MetadataEnricher")

        self._settings = settings
        me = settings.ingestion.metadata_enricher
        self._use_llm = bool(me and me.use_llm)

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
            logger.warning("Metadata enrichment prompt missing at %s; using builtin", path)
            return _BUILTIN_PROMPT
        text = raw.strip()
        if "{text}" not in text:
            text = text.rstrip() + "\n\n{text}"
        return text

    def transform(
        self, chunks: List[Chunk], trace: Optional[TraceContext] = None
    ) -> List[Chunk]:
        if trace is not None:
            trace.record_stage(
                "metadata_enricher",
                chunk_count=len(chunks),
                use_llm=self._use_llm,
            )

        out: List[Chunk] = []
        for chunk in chunks:
            try:
                out.append(self._enrich_one(chunk, trace))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Metadata enrichment failed for %s", chunk.id)
                md = dict(chunk.metadata)
                t, s, g = _rule_title_summary_tags(chunk.text)
                md["title"] = t
                md["summary"] = s
                md["tags"] = g
                md["enriched_by"] = "rule"
                md["metadata_enrichment_error"] = str(exc)
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

    def _enrich_one(self, chunk: Chunk, trace: Optional[TraceContext]) -> Chunk:
        rule_t, rule_s, rule_g = _rule_title_summary_tags(chunk.text)
        title, summary, tags = rule_t, rule_s, rule_g
        enriched_by = "rule"
        fallback_reason: Optional[str] = None

        if self._use_llm and self._llm is not None:
            llm_vals = self._llm_enrich(chunk.text, trace)
            if llm_vals is not None:
                title, summary, tags = llm_vals
                enriched_by = "llm"
            else:
                fallback_reason = "llm_failed_or_invalid"

        md = dict(chunk.metadata)
        md["title"] = title
        md["summary"] = summary
        md["tags"] = tags
        md["enriched_by"] = enriched_by
        if fallback_reason:
            md["metadata_enrichment_fallback_reason"] = fallback_reason

        return Chunk(
            id=chunk.id,
            text=chunk.text,
            metadata=md,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            source_ref=chunk.source_ref,
        )

    def _llm_enrich(
        self, text: str, trace: Optional[TraceContext]
    ) -> Optional[Tuple[str, str, List[str]]]:
        prompt = self._prompt_template.format(text=text)
        assert self._llm is not None
        try:
            out = self._llm.generate(prompt)
        except Exception as exc:  # noqa: BLE001
            if trace is not None:
                trace.record_stage("metadata_enricher_llm_error", error=str(exc))
            logger.warning("LLM metadata enrichment failed: %s", exc)
            return None
        if not isinstance(out, str) or not out.strip():
            return None
        parsed = _parse_llm_json(out)
        if parsed is None:
            if trace is not None:
                trace.record_stage("metadata_enricher_llm_invalid_json", output_chars=len(out))
            return None
        if trace is not None:
            trace.record_stage("metadata_enricher_llm_ok", output_chars=len(out))
        return parsed
