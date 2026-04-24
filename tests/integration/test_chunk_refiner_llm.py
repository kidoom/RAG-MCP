"""Real LLM calls for ChunkRefiner (opt-in: avoids CI cost)."""

from __future__ import annotations

import os

import pytest

from core.settings import load_settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.chunk_refiner import ChunkRefiner

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("CHUNK_REFINER_LLM_INTEGRATION") != "1",
    reason="Set CHUNK_REFINER_LLM_INTEGRATION=1 to run live LLM refinement tests",
)
def test_live_llm_refines_noisy_chunk(project_root):
    from dataclasses import replace

    from core.settings import ChunkRefinerSettings

    settings = load_settings(project_root / "config" / "settings.yaml")
    ing = settings.ingestion
    assert ing is not None
    ing2 = replace(
        ing,
        chunk_refiner=ChunkRefinerSettings(use_llm=True),
    )
    settings2 = replace(settings, ingestion=ing2)

    refiner = ChunkRefiner(settings2)
    noisy = (
        "CONFIDENTIAL\n\n<!-- noise -->\n\nPage 1 of 200\n\n"
        "The   product   supports   hybrid   retrieval.\n\n\n\n"
    )
    ch = Chunk(
        id="live-1",
        text=noisy,
        metadata={"source_path": str(project_root / "tests" / "data" / "live.pdf")},
        start_offset=0,
        end_offset=len(noisy),
    )
    tr = TraceContext()
    out = refiner.transform([ch], trace=tr)[0]

    assert out.metadata.get("refined_by") == "llm", "Expected LLM path; check API keys and provider"
    assert "hybrid" in out.text.lower() or "retrieval" in out.text.lower()
    assert "<!--" not in out.text
    assert tr.stages


@pytest.mark.skipif(
    os.environ.get("CHUNK_REFINER_LLM_INTEGRATION") != "1",
    reason="Set CHUNK_REFINER_LLM_INTEGRATION=1 for live LLM tests",
)
def test_live_llm_invalid_config_degrades(project_root):
    """Broken model still must not crash ingestion path."""
    from dataclasses import replace

    from core.settings import ChunkRefinerSettings

    settings = load_settings(project_root / "config" / "settings.yaml")
    ing = settings.ingestion
    assert ing is not None
    ing2 = replace(
        ing,
        chunk_refiner=ChunkRefinerSettings(use_llm=True),
    )
    bad_llm = replace(settings.llm, model="__definitely_invalid_model_name__")
    settings2 = replace(settings, llm=bad_llm, ingestion=ing2)

    refiner = ChunkRefiner(settings2)
    ch = Chunk(
        id="live-2",
        text="Hello   world",
        metadata={"source_path": "/x.pdf"},
        start_offset=0,
        end_offset=12,
    )
    out = refiner.transform([ch])[0]
    assert out.metadata["refined_by"] == "rule"
    assert out.metadata.get("refinement_fallback_reason") == "llm_failed_or_empty"
