"""Configuration loading and validation for the Modular RAG MCP Server.

This module provides:
- Settings dataclass for configuration structure
- load_settings() function to read YAML files
- validate_settings() to check required fields
- SettingsError for configuration errors
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

# ---------------------------------------------------------------------------
# Repo root & path resolution
# ---------------------------------------------------------------------------
# Anchored to this file's location: <repo>/src/core/settings.py → parents[2]
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# Default absolute path to settings.yaml
DEFAULT_SETTINGS_PATH: Path = REPO_ROOT / "config" / "settings.yaml"


def resolve_path(relative: Union[str, Path]) -> Path:
    """Resolve a repo-relative path to an absolute path.

    If *relative* is already absolute it is returned as-is.  Otherwise
    it is resolved against :data:`REPO_ROOT`.

    Args:
        relative: Relative or absolute path

    Returns:
        Absolute path resolved against repository root

    Example:
        >>> resolve_path("config/settings.yaml")  # doctest: +SKIP
        PosixPath('/home/user/Modular-RAG-MCP-Server/config/settings.yaml')
    """
    p = Path(relative)
    if p.is_absolute():
        return p
    return (REPO_ROOT / p).resolve()


class SettingsError(ValueError):
    """Raised when settings validation fails."""

    pass


# ---------------------------------------------------------------------------
# Helper functions for type validation
# ---------------------------------------------------------------------------


def _require_mapping(data: Dict[str, Any], key: str, path: str) -> Dict[str, Any]:
    """Extract required mapping from configuration.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        path: Dotted path for error messages

    Returns:
        Dictionary value

    Raises:
        SettingsError: If key is missing or not a mapping
    """
    value = data.get(key)
    if value is None:
        raise SettingsError(f"Missing required field: {path}.{key}")
    if not isinstance(value, dict):
        raise SettingsError(f"Expected mapping for field: {path}.{key}")
    return value


def _require_value(data: Dict[str, Any], key: str, path: str) -> Any:
    """Extract required value from configuration.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        path: Dotted path for error messages

    Returns:
        Any value

    Raises:
        SettingsError: If key is missing or value is None
    """
    if key not in data or data.get(key) is None:
        raise SettingsError(f"Missing required field: {path}.{key}")
    return data[key]


def _require_str(data: Dict[str, Any], key: str, path: str) -> str:
    """Extract required string from configuration.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        path: Dotted path for error messages

    Returns:
        String value

    Raises:
        SettingsError: If key is missing or value is not a non-empty string
    """
    value = _require_value(data, key, path)
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"Expected non-empty string for field: {path}.{key}")
    return value


def _require_int(data: Dict[str, Any], key: str, path: str) -> int:
    """Extract required integer from configuration.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        path: Dotted path for error messages

    Returns:
        Integer value

    Raises:
        SettingsError: If key is missing or value is not an integer
    """
    value = _require_value(data, key, path)
    if not isinstance(value, int):
        raise SettingsError(f"Expected integer for field: {path}.{key}")
    return value


def _require_number(data: Dict[str, Any], key: str, path: str) -> float:
    """Extract required number (int or float) from configuration.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        path: Dotted path for error messages

    Returns:
        Float value

    Raises:
        SettingsError: If key is missing or value is not numeric
    """
    value = _require_value(data, key, path)
    if not isinstance(value, (int, float)):
        raise SettingsError(f"Expected number for field: {path}.{key}")
    return float(value)


def _require_bool(data: Dict[str, Any], key: str, path: str) -> bool:
    """Extract required boolean from configuration.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        path: Dotted path for error messages

    Returns:
        Boolean value

    Raises:
        SettingsError: If key is missing or value is not a boolean
    """
    value = _require_value(data, key, path)
    if not isinstance(value, bool):
        raise SettingsError(f"Expected boolean for field: {path}.{key}")
    return value


def _require_list(data: Dict[str, Any], key: str, path: str) -> List[Any]:
    """Extract required list from configuration.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        path: Dotted path for error messages

    Returns:
        List value

    Raises:
        SettingsError: If key is missing or value is not a list
    """
    value = _require_value(data, key, path)
    if not isinstance(value, list):
        raise SettingsError(f"Expected list for field: {path}.{key}")
    return value


def _get_str(data: Dict[str, Any], key: str, default: str = "") -> str:
    """Extract optional string from configuration with default.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        default: Default value if key is missing

    Returns:
        String value or default
    """
    return data.get(key, default)


def _get_bool(data: Dict[str, Any], key: str, default: bool = False) -> bool:
    """Extract optional boolean from configuration with default.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        default: Default value if key is missing

    Returns:
        Boolean value or default
    """
    return data.get(key, default)


def _get_int(data: Dict[str, Any], key: str, default: int = 0) -> int:
    """Extract optional integer from configuration with default.

    Args:
        data: Dictionary to extract from
        key: Key to look for
        default: Default value if key is missing

    Returns:
        Integer value or default
    """
    return data.get(key, default)


# ---------------------------------------------------------------------------
# Settings dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMSettings:
    """LLM provider configuration."""

    provider: str
    model: str
    temperature: float
    max_tokens: int
    api_key: str = ""
    base_url: str = ""
    azure_endpoint: str = ""
    deployment_name: str = ""
    api_version: str = ""


@dataclass(frozen=True)
class EmbeddingSettings:
    """Embedding model configuration."""

    provider: str
    model: str
    dimensions: int
    api_key: str = ""
    base_url: str = ""
    azure_endpoint: str = ""
    deployment_name: str = ""
    api_version: str = ""


@dataclass(frozen=True)
class VectorStoreSettings:
    """Vector store configuration."""

    provider: str
    persist_directory: str
    collection_name: str = "default"


@dataclass(frozen=True)
class RetrievalSettings:
    """Retrieval configuration."""

    dense_top_k: int
    sparse_top_k: int
    fusion_top_k: int
    rrf_k: int = 60


@dataclass(frozen=True)
class RerankSettings:
    """Reranker configuration."""

    enabled: bool
    provider: str
    model: str = ""
    top_k: int = 5


@dataclass(frozen=True)
class EvaluationSettings:
    """Evaluation configuration."""

    enabled: bool
    provider: str
    metrics: List[str]


@dataclass(frozen=True)
class ObservabilitySettings:
    """Observability and logging configuration."""

    log_level: str
    trace_enabled: bool
    trace_file: str
    structured_logging: bool


@dataclass(frozen=True)
class VisionLLMSettings:
    """Vision LLM configuration for image captioning."""

    enabled: bool
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    azure_endpoint: str = ""
    deployment_name: str = ""
    api_version: str = ""
    max_image_size: int = 2048


@dataclass(frozen=True)
class ChunkRefinerSettings:
    """Chunk text refinement (rule + optional LLM)."""

    use_llm: bool = False


@dataclass(frozen=True)
class MetadataEnricherSettings:
    """Chunk metadata enrichment (rule + optional LLM)."""

    use_llm: bool = False


@dataclass(frozen=True)
class ImageCaptionerSettings:
    """Image captioning (optional Vision LLM; graceful fallback)."""

    use_vision_llm: bool = False


@dataclass(frozen=True)
class IngestionSettings:
    """Ingestion pipeline configuration."""

    chunk_size: int
    chunk_overlap: int
    splitter: str
    batch_size: int
    chunk_refiner: Optional[ChunkRefinerSettings] = None
    metadata_enricher: Optional[MetadataEnricherSettings] = None
    image_captioner: Optional[ImageCaptionerSettings] = None


@dataclass(frozen=True)
class Settings:
    """Complete settings configuration."""

    llm: LLMSettings
    embedding: EmbeddingSettings
    vector_store: VectorStoreSettings
    retrieval: RetrievalSettings
    rerank: RerankSettings
    evaluation: EvaluationSettings
    observability: ObservabilitySettings
    vision_llm: VisionLLMSettings
    ingestion: Optional[IngestionSettings] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        """Create Settings from dictionary (typically from YAML).

        Args:
            data: Configuration dictionary

        Returns:
            Settings instance

        Raises:
            SettingsError: If required fields are missing or invalid
        """
        if not isinstance(data, dict):
            raise SettingsError("Settings root must be a mapping")

        llm = _require_mapping(data, "llm", "settings")
        embedding = _require_mapping(data, "embedding", "settings")
        vector_store = _require_mapping(data, "vector_store", "settings")
        retrieval = _require_mapping(data, "retrieval", "settings")
        rerank = _require_mapping(data, "rerank", "settings")
        evaluation = _require_mapping(data, "evaluation", "settings")
        observability = _require_mapping(data, "observability", "settings")
        vision_llm = _require_mapping(data, "vision_llm", "settings")

        ingestion_settings = None
        if "ingestion" in data:
            ingestion = _require_mapping(data, "ingestion", "settings")
            chunk_refiner: Optional[ChunkRefinerSettings] = None
            if "chunk_refiner" in ingestion and ingestion["chunk_refiner"] is not None:
                cr = ingestion["chunk_refiner"]
                if not isinstance(cr, dict):
                    raise SettingsError("ingestion.chunk_refiner must be a mapping when present")
                chunk_refiner = ChunkRefinerSettings(
                    use_llm=_require_bool(cr, "use_llm", "ingestion.chunk_refiner"),
                )
            metadata_enricher: Optional[MetadataEnricherSettings] = None
            if "metadata_enricher" in ingestion and ingestion["metadata_enricher"] is not None:
                me = ingestion["metadata_enricher"]
                if not isinstance(me, dict):
                    raise SettingsError("ingestion.metadata_enricher must be a mapping when present")
                metadata_enricher = MetadataEnricherSettings(
                    use_llm=_require_bool(me, "use_llm", "ingestion.metadata_enricher"),
                )
            image_captioner: Optional[ImageCaptionerSettings] = None
            if "image_captioner" in ingestion and ingestion["image_captioner"] is not None:
                ic = ingestion["image_captioner"]
                if not isinstance(ic, dict):
                    raise SettingsError("ingestion.image_captioner must be a mapping when present")
                image_captioner = ImageCaptionerSettings(
                    use_vision_llm=_require_bool(
                        ic, "use_vision_llm", "ingestion.image_captioner"
                    ),
                )
            ingestion_settings = IngestionSettings(
                chunk_size=_require_int(ingestion, "chunk_size", "ingestion"),
                chunk_overlap=_require_int(ingestion, "chunk_overlap", "ingestion"),
                splitter=_require_str(ingestion, "splitter", "ingestion"),
                batch_size=_require_int(ingestion, "batch_size", "ingestion"),
                chunk_refiner=chunk_refiner,
                metadata_enricher=metadata_enricher,
                image_captioner=image_captioner,
            )

        settings = cls(
            llm=LLMSettings(
                provider=_require_str(llm, "provider", "llm"),
                model=_require_str(llm, "model", "llm"),
                temperature=_require_number(llm, "temperature", "llm"),
                max_tokens=_require_int(llm, "max_tokens", "llm"),
                api_key=_get_str(llm, "api_key"),
                base_url=_get_str(llm, "base_url"),
                azure_endpoint=_get_str(llm, "azure_endpoint"),
                deployment_name=_get_str(llm, "deployment_name"),
                api_version=_get_str(llm, "api_version"),
            ),
            embedding=EmbeddingSettings(
                provider=_require_str(embedding, "provider", "embedding"),
                model=_require_str(embedding, "model", "embedding"),
                dimensions=_require_int(embedding, "dimensions", "embedding"),
                api_key=_get_str(embedding, "api_key"),
                base_url=_get_str(embedding, "base_url"),
                azure_endpoint=_get_str(embedding, "azure_endpoint"),
                deployment_name=_get_str(embedding, "deployment_name"),
                api_version=_get_str(embedding, "api_version"),
            ),
            vector_store=VectorStoreSettings(
                provider=_require_str(vector_store, "provider", "vector_store"),
                persist_directory=_require_str(vector_store, "persist_directory", "vector_store"),
                collection_name=_get_str(vector_store, "collection_name", "default"),
            ),
            retrieval=RetrievalSettings(
                dense_top_k=_require_int(retrieval, "dense_top_k", "retrieval"),
                sparse_top_k=_require_int(retrieval, "sparse_top_k", "retrieval"),
                fusion_top_k=_require_int(retrieval, "fusion_top_k", "retrieval"),
                rrf_k=_get_int(retrieval, "rrf_k", 60),
            ),
            rerank=RerankSettings(
                enabled=_require_bool(rerank, "enabled", "rerank"),
                provider=_require_str(rerank, "provider", "rerank"),
                model=_get_str(rerank, "model"),
                top_k=_get_int(rerank, "top_k", 5),
            ),
            evaluation=EvaluationSettings(
                enabled=_require_bool(evaluation, "enabled", "evaluation"),
                provider=_require_str(evaluation, "provider", "evaluation"),
                metrics=[str(item) for item in _require_list(evaluation, "metrics", "evaluation")],
            ),
            observability=ObservabilitySettings(
                log_level=_require_str(observability, "log_level", "observability"),
                trace_enabled=_require_bool(observability, "trace_enabled", "observability"),
                trace_file=_require_str(observability, "trace_file", "observability"),
                structured_logging=_require_bool(observability, "structured_logging", "observability"),
            ),
            vision_llm=VisionLLMSettings(
                enabled=_require_bool(vision_llm, "enabled", "vision_llm"),
                provider=_require_str(vision_llm, "provider", "vision_llm"),
                model=_require_str(vision_llm, "model", "vision_llm"),
                api_key=_get_str(vision_llm, "api_key"),
                base_url=_get_str(vision_llm, "base_url"),
                azure_endpoint=_get_str(vision_llm, "azure_endpoint"),
                deployment_name=_get_str(vision_llm, "deployment_name"),
                api_version=_get_str(vision_llm, "api_version"),
                max_image_size=_get_int(vision_llm, "max_image_size", 2048),
            ),
            ingestion=ingestion_settings,
        )

        return settings


def validate_settings(settings: Settings) -> None:
    """Validate settings and raise SettingsError if invalid.

    Checks that all required fields have non-empty values.

    Args:
        settings: Settings instance to validate

    Raises:
        SettingsError: If validation fails
    """
    if not settings.llm.provider:
        raise SettingsError("Missing required field: llm.provider")
    if not settings.embedding.provider:
        raise SettingsError("Missing required field: embedding.provider")
    if not settings.vector_store.provider:
        raise SettingsError("Missing required field: vector_store.provider")
    if not settings.retrieval.rrf_k:
        raise SettingsError("Missing required field: retrieval.rrf_k")
    if not settings.rerank.provider:
        raise SettingsError("Missing required field: rerank.provider")
    if not settings.evaluation.provider:
        raise SettingsError("Missing required field: evaluation.provider")
    if not settings.observability.log_level:
        raise SettingsError("Missing required field: observability.log_level")


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings from a YAML file and validate required fields.

    Args:
        path: Path to settings YAML. Defaults to
            ``<repo>/config/settings.yaml`` (absolute, CWD-independent).

    Returns:
        Validated Settings instance

    Raises:
        SettingsError: If file not found, invalid YAML, or validation fails
    """
    settings_path = Path(path) if path is not None else DEFAULT_SETTINGS_PATH
    if not settings_path.is_absolute():
        settings_path = resolve_path(settings_path)
    if not settings_path.exists():
        raise SettingsError(f"Settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)

    settings = Settings.from_dict(data or {})
    validate_settings(settings)
    return settings
