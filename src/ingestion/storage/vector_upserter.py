"""Vector upsert adapter for dense records (C12)."""

from __future__ import annotations

import hashlib
from typing import List, Optional

from core.settings import Settings
from core.trace.trace_context import TraceContext
from core.types import ChunkRecord
from libs.vector_store import (
    BaseVectorStore,
    VectorRecord,
    VectorStoreFactory,
    VectorStoreSettings,
)


def _lib_vector_settings_from_core(settings: Settings) -> VectorStoreSettings:
    cfg = settings.vector_store
    return VectorStoreSettings(
        provider=cfg.provider,
        persist_directory=cfg.persist_directory,
        collection_name=cfg.collection_name,
    )


class VectorUpserter:
    """Persist dense vectors with deterministic chunk IDs."""
    # 将稠密向量存储到向量数据库中，并生成确定性的 chunk_id 用于后续的检索         

    def __init__(self, settings: Settings, vector_store: Optional[BaseVectorStore] = None):
        # 初始化向量存储
        self._settings = settings
        self._vector_store = vector_store or VectorStoreFactory.create(
            _lib_vector_settings_from_core(settings)
        )

    @staticmethod
    def build_chunk_id(record: ChunkRecord) -> str:
        """Build deterministic chunk id from source path, chunk index and content hash."""
        source_path = str(record.metadata.get("source_path", "")).strip()
        if not source_path:
            raise ValueError("ChunkRecord.metadata['source_path'] is required for upsert")
        chunk_index = record.metadata.get("chunk_index")
        if chunk_index is None:
            raise ValueError("ChunkRecord.metadata['chunk_index'] is required for upsert")
            # 计算内容哈希，用于后续的检索
        content_hash = hashlib.sha256(record.text.encode("utf-8")).hexdigest()[:8]
        # 将 source_path、chunk_index 和 content_hash 拼接起来，用于后续的检索
        raw = f"{source_path}|{int(chunk_index)}|{content_hash}"
        # 对 raw 进行哈希，生成确定性的 chunk_id，用于后续的检索    
        return hashlib.sha256(raw.encode("utf-8")).hexdigest() # 返回确定性的 chunk_id  

    def upsert(
        self, records: List[ChunkRecord], trace: Optional[TraceContext] = None
    ) -> List[ChunkRecord]:
        """Convert ChunkRecord list to VectorRecord and upsert in order."""
        if trace is not None:
            trace.record_stage(
                "vector_upserter",
                record_count=len(records),
                provider=self._settings.vector_store.provider,
                collection=self._settings.vector_store.collection_name,
            )

        if not records:
            return []

        upsert_records: List[VectorRecord] = []
        output_records: List[ChunkRecord] = []
        # 遍历每条记录，将稠密向量存储到向量数据库中，并生成确定性的 chunk_id 用于后续的检索
        for record in records:
            if not record.dense_vector:
                raise ValueError(
                    f"ChunkRecord[{record.id}] missing dense_vector; cannot upsert to vector store"
                )
            stable_id = self.build_chunk_id(record)
            normalized = ChunkRecord(
                id=stable_id,
                text=record.text,
                metadata=dict(record.metadata),
                dense_vector=[float(v) for v in record.dense_vector],
                sparse_vector=record.sparse_vector,
            )
            output_records.append(normalized)
            upsert_records.append(
                VectorRecord(
                    id=stable_id,
                    vector=normalized.dense_vector,
                    text=normalized.text,
                    metadata=normalized.metadata,
                )
            )

        self._vector_store.upsert(upsert_records, trace=trace)
        return output_records
