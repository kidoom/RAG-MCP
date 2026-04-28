"""Configuration reading service for the Dashboard UI."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from core.settings import Settings, load_settings


class ConfigService:
    """Encapsulates Settings reading and formats component config for display."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = load_settings()
        return self._settings

    def get_component_cards(self) -> List[Dict[str, Any]]:
        """Return a list of component configuration cards for the overview page."""
        s = self.settings
        return [
            {
                "name": "LLM",
                "icon": "🤖",
                "fields": {
                    "Provider": s.llm.provider,
                    "Model": s.llm.model,
                    "Temperature": str(s.llm.temperature),
                    "Max Tokens": str(s.llm.max_tokens),
                },
                "status": "active" if s.llm.provider else "inactive",
            },
            {
                "name": "Embedding",
                "icon": "🧮",
                "fields": {
                    "Provider": s.embedding.provider,
                    "Model": s.embedding.model,
                    "Dimensions": str(s.embedding.dimensions),
                },
                "status": "active" if s.embedding.provider else "inactive",
            },
            {
                "name": "Vector Store",
                "icon": "🗄️",
                "fields": {
                    "Provider": s.vector_store.provider,
                    "Persist Directory": s.vector_store.persist_directory,
                    "Collection": s.vector_store.collection_name,
                },
                "status": "active" if s.vector_store.provider else "inactive",
            },
            {
                "name": "Retrieval",
                "icon": "🔎",
                "fields": {
                    "Dense Top-K": str(s.retrieval.dense_top_k),
                    "Sparse Top-K": str(s.retrieval.sparse_top_k),
                    "Fusion Top-K": str(s.retrieval.fusion_top_k),
                    "RRF K": str(s.retrieval.rrf_k),
                },
                "status": "active",
            },
            {
                "name": "Reranker",
                "icon": "📊",
                "fields": {
                    "Enabled": str(s.rerank.enabled),
                    "Provider": s.rerank.provider,
                    "Model": s.rerank.model or "(default)",
                    "Top-K": str(s.rerank.top_k),
                },
                "status": "active" if s.rerank.enabled else "inactive",
            },
            {
                "name": "Evaluation",
                "icon": "📈",
                "fields": {
                    "Enabled": str(s.evaluation.enabled),
                    "Provider": s.evaluation.provider,
                    "Metrics": ", ".join(s.evaluation.metrics),
                },
                "status": "active" if s.evaluation.enabled else "inactive",
            },
            {
                "name": "Observability",
                "icon": "👁️",
                "fields": {
                    "Log Level": s.observability.log_level,
                    "Trace Enabled": str(s.observability.trace_enabled),
                    "Trace File": s.observability.trace_file,
                },
                "status": "active",
            },
            {
                "name": "Vision LLM",
                "icon": "👁️‍🗨️",
                "fields": {
                    "Enabled": str(s.vision_llm.enabled),
                    "Provider": s.vision_llm.provider,
                    "Model": s.vision_llm.model,
                },
                "status": "active" if s.vision_llm.enabled else "inactive",
            },
        ]

    def get_ingestion_config(self) -> Dict[str, Any] | None:
        s = self.settings
        if s.ingestion is None:
            return None
        return {
            "Chunk Size": str(s.ingestion.chunk_size),
            "Chunk Overlap": str(s.ingestion.chunk_overlap),
            "Splitter": s.ingestion.splitter,
            "Batch Size": str(s.ingestion.batch_size),
            "Chunk Refiner (LLM)": (
                str(s.ingestion.chunk_refiner.use_llm)
                if s.ingestion.chunk_refiner
                else "N/A"
            ),
            "Metadata Enricher (LLM)": (
                str(s.ingestion.metadata_enricher.use_llm)
                if s.ingestion.metadata_enricher
                else "N/A"
            ),
            "Image Captioner (Vision LLM)": (
                str(s.ingestion.image_captioner.use_vision_llm)
                if s.ingestion.image_captioner
                else "N/A"
            ),
        }
