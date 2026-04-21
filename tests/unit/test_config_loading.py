"""Tests for settings loading and validation.

Unit tests for:
- load_settings() function
- Settings dataclass creation
- validate_settings() function
- Error handling for missing/invalid fields
"""

from __future__ import annotations

from pathlib import Path
import textwrap

import pytest

from src.core.settings import SettingsError, load_settings, Settings


def _write_yaml(path: Path, content: str) -> None:
    """Helper to write YAML content to file."""
    path.write_text(content, encoding="utf-8")


def test_load_settings_success(tmp_path: Path) -> None:
    """Test successful loading of valid settings."""
    config = textwrap.dedent("""
      llm:
        provider: openai
        model: gpt-4
        temperature: 0.3
        max_tokens: 2048
      embedding:
        provider: openai
        model: text-embedding-3-small
        dimensions: 1536
      vector_store:
        provider: chroma
        persist_directory: ./data/db/chroma
        collection_name: knowledge_hub
      retrieval:
        dense_top_k: 20
        sparse_top_k: 20
        fusion_top_k: 10
        rrf_k: 60
      rerank:
        enabled: false
        provider: none
        top_k: 5
      evaluation:
        enabled: false
        provider: custom
        metrics:
          - hit_rate
          - mrr
      observability:
        log_level: INFO
        trace_enabled: true
        trace_file: ./logs/traces.jsonl
        structured_logging: true
      vision_llm:
        enabled: true
        provider: openai
        model: gpt-4-vision
        max_image_size: 2048
      ingestion:
        chunk_size: 1000
        chunk_overlap: 200
        splitter: recursive
        batch_size: 100
    """
    )
    settings_path = tmp_path / "settings.yaml"
    _write_yaml(settings_path, config)

    settings = load_settings(settings_path)

    assert settings.llm.provider == "openai"
    assert settings.embedding.dimensions == 1536
    assert settings.vector_store.collection_name == "knowledge_hub"
    assert settings.retrieval.rrf_k == 60
    assert settings.rerank.provider == "none"
    assert settings.evaluation.metrics == ["hit_rate", "mrr"]
    assert settings.observability.log_level == "INFO"
    assert settings.ingestion is not None
    assert settings.ingestion.chunk_size == 1000


def test_missing_required_field_raises_error(tmp_path: Path) -> None:
    """Test that missing required field raises SettingsError."""
    config = textwrap.dedent("""
      llm:
        provider: openai
        model: gpt-4
        temperature: 0.3
        max_tokens: 2048
      # Missing embedding section
      vector_store:
        provider: chroma
        persist_directory: ./data/db/chroma
      retrieval:
        dense_top_k: 20
        sparse_top_k: 20
        fusion_top_k: 10
      rerank:
        enabled: false
        provider: none
      evaluation:
        enabled: false
        provider: custom
        metrics: [hit_rate]
      observability:
        log_level: INFO
        trace_enabled: true
        trace_file: ./logs/traces.jsonl
        structured_logging: true
      vision_llm:
        enabled: false
        provider: none
        model: none
    """
    )
    settings_path = tmp_path / "settings.yaml"
    _write_yaml(settings_path, config)

    with pytest.raises(SettingsError, match="embedding"):
        load_settings(settings_path)


def test_missing_llm_provider_raises_error(tmp_path: Path) -> None:
    """Test that missing llm.provider raises SettingsError."""
    config = textwrap.dedent("""
      llm:
        # Missing provider
        model: gpt-4
        temperature: 0.3
        max_tokens: 2048
      embedding:
        provider: openai
        model: text-embedding-3-small
        dimensions: 1536
      vector_store:
        provider: chroma
        persist_directory: ./data/db/chroma
      retrieval:
        dense_top_k: 20
        sparse_top_k: 20
        fusion_top_k: 10
      rerank:
        enabled: false
        provider: none
      evaluation:
        enabled: false
        provider: custom
        metrics: [hit_rate]
      observability:
        log_level: INFO
        trace_enabled: true
        trace_file: ./logs/traces.jsonl
        structured_logging: true
      vision_llm:
        enabled: false
        provider: none
        model: none
    """
    )
    settings_path = tmp_path / "settings.yaml"
    _write_yaml(settings_path, config)

    with pytest.raises(SettingsError, match="llm.provider"):
        load_settings(settings_path)


def test_missing_embedding_provider_raises_error(tmp_path: Path) -> None:
    """Test that missing embedding.provider raises SettingsError."""
    config = textwrap.dedent("""
      llm:
        provider: openai
        model: gpt-4
        temperature: 0.3
        max_tokens: 2048
      embedding:
        # Missing provider
        model: text-embedding-3-small
        dimensions: 1536
      vector_store:
        provider: chroma
        persist_directory: ./data/db/chroma
      retrieval:
        dense_top_k: 20
        sparse_top_k: 20
        fusion_top_k: 10
      rerank:
        enabled: false
        provider: none
      evaluation:
        enabled: false
        provider: custom
        metrics: [hit_rate]
      observability:
        log_level: INFO
        trace_enabled: true
        trace_file: ./logs/traces.jsonl
        structured_logging: true
      vision_llm:
        enabled: false
        provider: none
        model: none
    """
    )
    settings_path = tmp_path / "settings.yaml"
    _write_yaml(settings_path, config)

    with pytest.raises(SettingsError, match="embedding.provider"):
        load_settings(settings_path)


def test_missing_settings_file_raises_error(tmp_path: Path) -> None:
    """Test that missing settings file raises SettingsError."""
    nonexistent_path = tmp_path / "nonexistent.yaml"
    
    with pytest.raises(SettingsError, match="Settings file not found"):
        load_settings(nonexistent_path)


def test_invalid_yaml_raises_error(tmp_path: Path) -> None:
    """Test that invalid YAML raises error."""
    settings_path = tmp_path / "settings.yaml"
    _write_yaml(settings_path, "invalid: yaml: content: [")
    
    with pytest.raises(Exception):  # yaml.YAMLError or similar
        load_settings(settings_path)


@pytest.mark.unit
class TestSettingsDataclass:
    """Test Settings dataclass functionality."""

    def test_settings_frozen(self) -> None:
        """Test that Settings is immutable (frozen)."""
        from src.core.settings import LLMSettings, EmbeddingSettings, VectorStoreSettings
        from src.core.settings import RetrievalSettings, RerankSettings, EvaluationSettings
        from src.core.settings import ObservabilitySettings, VisionLLMSettings, Settings

        settings = Settings(
            llm=LLMSettings(provider="test", model="test", temperature=0.5, max_tokens=1000),
            embedding=EmbeddingSettings(provider="test", model="test", dimensions=768),
            vector_store=VectorStoreSettings(provider="test", persist_directory="./test"),
            retrieval=RetrievalSettings(dense_top_k=10, sparse_top_k=10, fusion_top_k=5),
            rerank=RerankSettings(enabled=False, provider="none"),
            evaluation=EvaluationSettings(enabled=False, provider="custom", metrics=[]),
            observability=ObservabilitySettings(
                log_level="INFO", trace_enabled=False, trace_file="./logs", structured_logging=False
            ),
            vision_llm=VisionLLMSettings(enabled=False, provider="none", model="none"),
        )

        # Should raise AttributeError when trying to modify frozen dataclass
        with pytest.raises(AttributeError):
            settings.llm = None  # type: ignore


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
