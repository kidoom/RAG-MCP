"""LLM-based reranker using a prompt template from config/prompts/rerank.txt."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..llm.base_llm import BaseLLM
from .base_reranker import BaseReranker, RerankerSettings

_DEFAULT_PROMPT_PATH = Path(__file__).resolve().parents[3] / "config" / "prompts" / "rerank.txt"

RERANK_FALLBACK_KEY = "_rerank_fallback"
RERANK_FALLBACK_REASON_KEY = "_rerank_fallback_reason"


def _strip_hash_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def _extract_json_object(raw: str) -> Dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM rerank response is not valid JSON: {exc}; first 200 chars: {text[:200]!r}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"LLM rerank response must be a JSON object, got {type(data).__name__}"
        )
    return data


class LLMReranker(BaseReranker):
    """Rerank candidates by asking an LLM for a strict `ranked_ids` ordering."""

    def __init__(self, settings: RerankerSettings, llm: BaseLLM):
        super().__init__(settings)
        self._llm = llm

    def _load_prompt_template(self) -> str:
        inline = self.settings.extra.get("rerank_prompt_template")
        if inline is not None:
            return str(inline)
        path = self.settings.extra.get("rerank_prompt_path")
        if path is None:
            path = _DEFAULT_PROMPT_PATH
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Rerank prompt file not found: {p}")
        return _strip_hash_comments(p.read_text(encoding="utf-8"))

    def _build_prompt(self, query: str, candidates: List[Dict[str, Any]]) -> str:
        template = self._load_prompt_template().rstrip()
        payload = [
            {
                "id": c["id"],
                "text": str(c.get("text", ""))[:4000],
            }
            for c in candidates
        ]
        instruction = (
            "\n\nCandidate documents (JSON):\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
            "Respond with ONLY a JSON object (no markdown) of the form:\n"
            '{"ranked_ids": ["<id>", ...]}\n'
            "The list must contain each candidate id exactly once, ordered from most to least relevant."
        )
        if template.endswith("Query:"):
            return f"{template} {query}{instruction}"
        return f"{template}\n\nQuery:\n{query}{instruction}"

    def _parse_ranked_ids(self, raw: str, expected: List[str]) -> List[str]:
        data = _extract_json_object(raw)
        if "ranked_ids" not in data:
            raise ValueError(
                "LLM rerank JSON must contain key 'ranked_ids' "
                f"(keys found: {sorted(data.keys())})"
            )
        ranked = data["ranked_ids"]
        if not isinstance(ranked, list):
            raise ValueError(
                f"LLM rerank 'ranked_ids' must be a list, got {type(ranked).__name__}"
            )
        if not all(isinstance(x, str) for x in ranked):
            raise ValueError("LLM rerank 'ranked_ids' must be a list of strings")

        if len(ranked) != len(set(ranked)):
            raise ValueError("LLM rerank 'ranked_ids' contains duplicate ids")

        exp_set = set(expected)
        ranked_set = set(ranked)
        if len(ranked) != len(expected) or ranked_set != exp_set:
            missing = exp_set - ranked_set
            extra = ranked_set - exp_set
            raise ValueError(
                "LLM rerank 'ranked_ids' must be a permutation of candidate ids "
                f"(expected {len(expected)} ids); missing={sorted(missing)!r} extra={sorted(extra)!r}"
            )

        return ranked

    def _resolve_top_k(self, top_k: Optional[int], n: int) -> int:
        if top_k is not None:
            return min(top_k, n)
        if self.settings.top_k is not None:
            return min(self.settings.top_k, n)
        return n

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        trace: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        for i, c in enumerate(candidates):
            if "id" not in c:
                raise ValueError(f"candidates[{i}] is missing required 'id' key")

        if len(candidates) == 1:
            return [dict(candidates[0])]

        k = self._resolve_top_k(None, len(candidates))
        ids = [str(c["id"]) for c in candidates]
        id_to_row = {str(c["id"]): dict(c) for c in candidates}

        prompt = self._build_prompt(query, candidates)
        try:
            raw = self._llm.generate(prompt)
        except Exception as exc:  # noqa: BLE001 — intentional fallback for any LLM failure
            out = [dict(c) for c in candidates[:k]]
            if out:
                out[0][RERANK_FALLBACK_KEY] = True
                out[0][RERANK_FALLBACK_REASON_KEY] = str(exc)
            return out

        ranked_ids = self._parse_ranked_ids(raw, ids)
        ordered = [id_to_row[i] for i in ranked_ids]
        return ordered[:k]
