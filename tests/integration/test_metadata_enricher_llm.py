"""Real LLM calls for MetadataEnricher (opt-in: avoids CI cost)."""

from __future__ import annotations

import os

import pytest

from core.settings import load_settings
from core.trace.trace_context import TraceContext
from core.types import Chunk
from ingestion.transform.metadata_enricher import MetadataEnricher

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    os.environ.get("METADATA_ENRICHER_LLM_INTEGRATION") != "1",
    reason="Set METADATA_ENRICHER_LLM_INTEGRATION=1 to run live LLM metadata tests",
)
def test_live_llm_enriches_chunk(project_root):
    from dataclasses import replace

    from core.settings import MetadataEnricherSettings

    settings = load_settings(project_root / "config" / "settings.yaml")
    ing = settings.ingestion
    assert ing is not None
    ing2 = replace(ing, metadata_enricher=MetadataEnricherSettings(use_llm=True))
    settings2 = replace(settings, ingestion=ing2)

    en = MetadataEnricher(settings2)
    body = (
        "Section: Retrieval\n\n"
        "The system combines dense vector search with BM25-style keyword search, "
        "then fuses results with RRF before optional reranking."
    )
    ch = Chunk(
        id="live-me-1",
        text=body,
        metadata={"source_path": str(project_root / "tests" / "data" / "live.pdf")},
        start_offset=0,
        end_offset=len(body),
    )
    tr = TraceContext()
    out = en.transform([ch], trace=tr)[0]

    assert out.metadata.get("enriched_by") == "llm", (
        "Expected LLM path; check API keys and provider in config/settings.yaml"
    )
    assert out.metadata.get("title")
    assert out.metadata.get("summary")
    assert isinstance(out.metadata.get("tags"), list) and out.metadata["tags"]
    tr_dump = tr.to_dict()
    assert tr_dump["stages"]


@pytest.mark.skipif(
    os.environ.get("METADATA_ENRICHER_LLM_INTEGRATION") != "1",
    reason="Set METADATA_ENRICHER_LLM_INTEGRATION=1 for live LLM tests",
)
def test_live_llm_invalid_config_degrades(project_root):
    from dataclasses import replace

    from core.settings import MetadataEnricherSettings

    settings = load_settings(project_root / "config" / "settings.yaml")
    ing = settings.ingestion
    assert ing is not None
    ing2 = replace(ing, metadata_enricher=MetadataEnricherSettings(use_llm=True))
    bad_llm = replace(settings.llm, model="__definitely_invalid_model_name__")
    settings2 = replace(settings, llm=bad_llm, ingestion=ing2)

    en = MetadataEnricher(settings2)
    ch = Chunk(
        id="live-me-2",
        text="Some text about databases and vectors.",
        metadata={"source_path": "/x.pdf"},
        start_offset=0,
        end_offset=40,
    )
    out = en.transform([ch])[0]
    assert out.metadata["enriched_by"] == "rule"
    assert out.metadata.get("metadata_enrichment_fallback_reason") == "llm_failed_or_invalid"
