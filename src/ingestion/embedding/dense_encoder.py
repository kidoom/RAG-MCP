"""Dense vector encoder for ingestion chunks."""

from __future__ import annotations

from typing import List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import Chunk, ChunkRecord
from libs.embedding import BaseEmbedding, EmbeddingFactory, EmbeddingSettings


def _lib_embedding_settings_from_core(settings: Settings) -> EmbeddingSettings:
    emb = settings.embedding
    return EmbeddingSettings(
        provider=emb.provider,
        model=emb.model,
        dimensions=int(emb.dimensions),
        api_key=emb.api_key or None,
        base_url=emb.base_url or None,
        azure_endpoint=emb.azure_endpoint or None,
        deployment_name=emb.deployment_name or None,
        api_version=emb.api_version or None,
    )


class DenseEncoder:
    """Encode chunks into dense vectors via libs.embedding providers."""

    def __init__(self, settings: Settings, embedding_client: Optional[BaseEmbedding] = None):
        if settings.ingestion is None:
            raise ValueError("Settings must contain 'ingestion' for DenseEncoder")
        self._settings = settings
        self._dimensions = int(settings.embedding.dimensions)
        self._batch_size = max(1, int(settings.ingestion.batch_size))
        self._embedding = embedding_client or EmbeddingFactory.create(
            _lib_embedding_settings_from_core(settings)
        )

    def encode(
        self, chunks: List[Chunk], trace: Optional[TraceContext] = None
    ) -> List[ChunkRecord]:
        if trace is not None:
            trace.record_stage(
                "dense_encoder",
                chunk_count=len(chunks),
                batch_size=self._batch_size,
                provider=self._settings.embedding.provider,
                model=self._settings.embedding.model,
            )

        if not chunks:
            return []

        out: List[ChunkRecord] = []
        for batch_idx, i in enumerate(range(0, len(chunks), self._batch_size)):
            batch = chunks[i : i + self._batch_size]
            texts = [c.text for c in batch]
            vectors = self._embedding.embed_texts(texts)
            if len(vectors) != len(batch):
                raise ValueError(
                    f"Embedding output size mismatch: expected {len(batch)}, got {len(vectors)}"
                )

            for chunk, vector in zip(batch, vectors):
                if len(vector) != self._dimensions:
                    raise ValueError(
                        f"Embedding dimension mismatch for chunk '{chunk.id}': "
                        f"expected {self._dimensions}, got {len(vector)}"
                    )
                out.append(
                    ChunkRecord(
                        id=chunk.id,
                        text=chunk.text,
                        metadata=dict(chunk.metadata),
                        dense_vector=[float(x) for x in vector],
                        sparse_vector=None,
                    )
                )

            if trace is not None:
                trace.record_stage(
                    "dense_encoder_batch",
                    batch_index=batch_idx,
                    encoded_count=len(batch),
                )

        return out
