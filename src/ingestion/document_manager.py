"""Document lifecycle management across all storage backends (G2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.settings import load_settings
from core.trace.trace_context import TraceContext
from ingestion.storage.bm25_indexer import BM25Indexer
from ingestion.storage.image_storage import ImageStorage
from libs.loader.file_integrity import FileIntegrityChecker, SQLiteIntegrityChecker
from libs.vector_store.base_vector_store import VectorStoreSettings
from libs.vector_store.chroma_store import ChromaStore


@dataclass
class DocumentInfo:
    """Summary info for a single ingested document."""

    source_path: str
    collection: str
    chunk_count: int
    image_count: int
    ingested_at: str = ""


@dataclass
class DocumentDetail:
    """Full detail for a single ingested document."""

    source_path: str
    collection: str
    doc_id: str
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    integrity_record: Optional[Dict[str, Any]] = None


@dataclass
class DeleteResult:
    """Result of a document deletion across stores."""

    source_path: str
    success: bool
    chroma_deleted: int = 0
    bm25_deleted: int = 0
    images_deleted: int = 0
    integrity_removed: bool = False
    errors: List[str] = field(default_factory=list)


@dataclass
class CollectionStats:
    """Aggregated stats across all storage backends."""

    collection_name: str
    chroma_entries: int = 0
    bm25_documents: int = 0
    images_stored: int = 0
    ingestion_records: int = 0


class DocumentManager:
    """Cross-storage document lifecycle management.

    Coordinates ChromaStore, BM25Indexer, ImageStorage, and FileIntegrityChecker
    for list / detail / delete / stats operations.
    """

    def __init__(
        self,
        chroma_store: Optional[ChromaStore] = None,
        bm25_indexer: Optional[BM25Indexer] = None,
        image_storage: Optional[ImageStorage] = None,
        integrity_checker: Optional[FileIntegrityChecker] = None,
    ):
        s = load_settings()
        vs_settings = VectorStoreSettings(
            provider=s.vector_store.provider,
            persist_directory=s.vector_store.persist_directory,
            collection_name=s.vector_store.collection_name,
        )
        self._chroma = chroma_store or ChromaStore(vs_settings)
        self._bm25 = bm25_indexer or BM25Indexer()
        self._images = image_storage or ImageStorage()
        self._integrity = integrity_checker or SQLiteIntegrityChecker()

    def list_documents(self, collection: Optional[str] = None) -> List[DocumentInfo]:
        """List all ingested documents, optionally filtered by collection."""
        self._bm25.load()

        source_map: Dict[str, Dict[str, Any]] = {}
        collections = (
            [collection] if collection else self._chroma.get_all_collections()
        )

        for coll_name in collections:
            # Query the actual ChromaDB collection — ChromaStore is bound to a
            # single default collection, so we must reach the PersistentClient.
            try:
                chroma_coll = self._chroma._client.get_collection(name=coll_name)
                response = chroma_coll.get(include=["documents", "metadatas"])
                results: List[Dict[str, Any]] = [
                    {
                        "id": str(item_id),
                        "text": text or "",
                        "metadata": meta or {},
                    }
                    for item_id, text, meta in zip(
                        response.get("ids") or [],
                        response.get("documents") or [],
                        response.get("metadatas") or [],
                    )
                ]
            except Exception:
                continue

            # Track source_path -> chunk_count and parent_doc_id
            seen_sources: Dict[str, int] = {}
            doc_id_by_source: Dict[str, str] = {}
            for r in results:
                md = r.get("metadata") or {}
                sp = md.get("source_path", "")
                if not sp:
                    continue
                seen_sources[sp] = seen_sources.get(sp, 0) + 1
                if sp not in doc_id_by_source:
                    doc_id_by_source[sp] = md.get("parent_doc_id", "")

            # Pre-fetch all images for this collection once
            try:
                all_imgs = self._images.list_images(coll_name)
            except Exception:
                all_imgs = []

            for sp, chunk_count in seen_sources.items():
                key = f"{coll_name}|{sp}"
                doc_hash = doc_id_by_source.get(sp, "")
                actual_img_count = sum(
                    1 for img in all_imgs
                    if doc_hash and img.get("doc_hash") == doc_hash
                )

                source_map[key] = {
                    "source_path": sp,
                    "collection": coll_name,
                    "chunk_count": chunk_count,
                    "image_count": actual_img_count,
                }

        history = self._integrity.list_processed()
        history_by_path: Dict[str, str] = {}
        for h in history:
            history_by_path[h["file_path"]] = h.get("processed_at", "")

        results: List[DocumentInfo] = []
        for info in source_map.values():
            info["ingested_at"] = history_by_path.get(info["source_path"], "")
            results.append(DocumentInfo(**info))

        results.sort(key=lambda x: (x.collection, x.source_path))
        return results

    def get_document_detail(self, doc_id: str, collection: Optional[str] = None) -> Optional[DocumentDetail]:
        """Get full detail for a document by its doc_id or source_path."""
        coll_name = collection or load_settings().vector_store.collection_name

        # Query the correct ChromaDB collection, not the default binding
        try:
            chroma_coll = self._chroma._client.get_collection(name=coll_name)
        except Exception:
            return None

        # Try source_path in metadata
        response = chroma_coll.get(
            where={"source_path": doc_id},
            include=["documents", "metadatas"],
        )
        ids = response.get("ids") or []
        docs = response.get("documents") or []
        metas = response.get("metadatas") or []
        results: List[Dict[str, Any]] = [
            {"id": str(i), "text": d or "", "metadata": m or {}}
            for i, d, m in zip(ids, docs, metas)
        ]

        if not results:
            # Try by ID prefix (via get)
            response = chroma_coll.get(
                ids=[doc_id],
                include=["documents", "metadatas"],
            )
            ids2 = response.get("ids") or []
            docs2 = response.get("documents") or []
            metas2 = response.get("metadatas") or []
            results = [
                {"id": str(i), "text": d or "", "metadata": m or {}}
                for i, d, m in zip(ids2, docs2, metas2)
            ]

        if not results:
            return None

        sp = ""
        for r in results:
            sp = r.get("metadata", {}).get("source_path", "") or sp
            if sp:
                break

        # Match images by parent_doc_id, not fragile substring
        doc_hash = ""
        for r in results:
            doc_hash = (r.get("metadata") or {}).get("parent_doc_id", "")
            if doc_hash:
                break

        images = self._images.list_images(coll_name)
        matching_images = [
            img for img in images
            if doc_hash and img.get("doc_hash") == doc_hash
        ]

        integrity_record = None
        for rec in self._integrity.list_processed():
            if rec["file_path"] == sp:
                integrity_record = rec
                break

        return DocumentDetail(
            source_path=sp or doc_id,
            collection=coll_name,
            doc_id=doc_id,
            chunks=results,
            images=matching_images,
            integrity_record=integrity_record,
        )

    def delete_document(
        self, source_path: str, collection: Optional[str] = None
    ) -> DeleteResult:
        """Delete a document from all storage backends."""
        coll_name = collection or load_settings().vector_store.collection_name
        result = DeleteResult(source_path=source_path, success=False)

        try:
            # 1. Delete from Chroma — use the correct collection
            chroma_coll = self._chroma._client.get_collection(name=coll_name)
            existing = chroma_coll.get(
                where={"source_path": source_path}, include=[]
            )
            ids_to_delete = existing.get("ids") or []
            if ids_to_delete:
                chroma_coll.delete(ids=ids_to_delete)
            result.chroma_deleted = len(ids_to_delete)
        except Exception as exc:
            result.errors.append(f"Chroma: {exc}")

        try:
            # 2. Delete from BM25 — find matching chunk_ids first
            self._bm25.load()
            bm25_ids = [
                cid for cid in self._bm25._doc_terms
                if source_path in cid or source_path in str(self._bm25._doc_terms.get(cid, {}))
            ]
            if bm25_ids:
                result.bm25_deleted = self._bm25.remove_documents(bm25_ids)
        except Exception as exc:
            result.errors.append(f"BM25: {exc}")

        try:
            # 3. Delete from ImageStorage
            # Find the doc hash from integrity records
            doc_hash = ""
            for rec in self._integrity.list_processed():
                if rec.get("file_path") == source_path:
                    if rec.get("status") == "success":
                        # Extract doc_id from error_msg field (used as message)
                        msg = rec.get("error_msg", "")
                        if "doc_id=" in msg:
                            doc_hash = msg.split("doc_id=")[1].split(";")[0]
                    break
            if doc_hash:
                result.images_deleted = self._images.delete_images(coll_name, doc_hash)
        except Exception as exc:
            result.errors.append(f"ImageStorage: {exc}")

        try:
            # 4. Remove from integrity checker
            for rec in self._integrity.list_processed():
                if rec.get("file_path") == source_path:
                    result.integrity_removed = self._integrity.remove_record(
                        rec["file_hash"]
                    )
                    break
        except Exception as exc:
            result.errors.append(f"Integrity: {exc}")

        result.success = (
            (result.chroma_deleted > 0 or result.bm25_deleted > 0)
            and not result.errors
        )
        return result

    def get_collection_stats(
        self, collection: Optional[str] = None
    ) -> CollectionStats:
        """Get aggregated statistics across all stores."""
        coll_name = collection or load_settings().vector_store.collection_name

        # Query the correct ChromaDB collection, not the default binding
        try:
            chroma_coll = self._chroma._client.get_collection(name=coll_name)
            chroma_count = chroma_coll.count()
        except Exception:
            chroma_count = 0
        self._bm25.load()

        import sqlite3

        from core.settings import REPO_ROOT

        img_count = 0
        try:
            img_db = REPO_ROOT / "data" / "db" / "image_index.db"
            if img_db.exists():
                conn = sqlite3.connect(str(img_db))
                row = conn.execute(
                    "SELECT COUNT(*) FROM image_index WHERE collection = ?",
                    (coll_name,),
                ).fetchone()
                if row:
                    img_count = row[0]
                conn.close()
        except Exception:
            pass

        ingestion_count = len(self._integrity.list_processed())

        return CollectionStats(
            collection_name=coll_name,
            chroma_entries=chroma_count,
            bm25_documents=self._bm25.doc_count,
            images_stored=img_count,
            ingestion_records=ingestion_count,
        )
