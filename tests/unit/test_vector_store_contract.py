import pytest

from src.libs.vector_store import (
    BaseVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreFactory,
    VectorStoreSettings,
)


class FakeVectorStore(BaseVectorStore):
    """Deterministic in-memory fake for contract testing."""

    def __init__(self, settings: VectorStoreSettings):
        super().__init__(settings)
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord], trace=None) -> None:
        for record in records:
            if not record.id:
                raise ValueError("VectorRecord.id cannot be empty")
            if not record.vector:
                raise ValueError("VectorRecord.vector cannot be empty")
            self.records[record.id] = record

    def query(self, vector: list[float], top_k: int, filters=None, trace=None) -> list[QueryResult]:
        if not vector:
            raise ValueError("query vector cannot be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        candidates = list(self.records.values())
        if filters:
            candidates = [
                record
                for record in candidates
                if all(record.metadata.get(key) == value for key, value in filters.items())
            ]

        def score(record: VectorRecord) -> float:
            common_dim = min(len(vector), len(record.vector))
            return sum(vector[i] * record.vector[i] for i in range(common_dim))

        ranked = sorted(candidates, key=score, reverse=True)[:top_k]
        return [
            QueryResult(
                id=record.id,
                score=score(record),
                text=record.text,
                metadata=record.metadata,
            )
            for record in ranked
        ]

    def get_by_ids(self, ids: list[str], trace=None) -> list[dict]:
        return [
            {
                "id": item_id,
                "text": self.records[item_id].text,
                "metadata": self.records[item_id].metadata,
            }
            for item_id in ids
            if item_id in self.records
        ]

    def get_by_metadata(self, filters: dict, trace=None) -> list[dict]:
        results = []
        for rid, record in self.records.items():
            match = True
            for k, v in (filters or {}).items():
                if record.metadata.get(k) != v:
                    match = False
                    break
            if match:
                results.append({
                    "id": rid,
                    "text": record.text,
                    "metadata": dict(record.metadata),
                })
        return results

    def delete_by_metadata(self, filters: dict, trace=None) -> int:
        if not filters:
            return 0
        to_delete = [
            rid for rid, record in self.records.items()
            if all(record.metadata.get(k) == v for k, v in filters.items())
        ]
        for rid in to_delete:
            del self.records[rid]
        return len(to_delete)

    def get_collection_stats(self, trace=None) -> dict:
        return {
            "collection_name": self.settings.collection_name,
            "entry_count": len(self.records),
        }

    def get_all_collections(self) -> list[str]:
        return [self.settings.collection_name]


class TestVectorStoreContract:
    def test_settings_creation(self):
        settings = VectorStoreSettings(
            provider="chroma",
            persist_directory="./data/db/chroma",
            collection_name="knowledge_hub",
        )
        assert settings.provider == "chroma"
        assert settings.persist_directory.endswith("chroma")
        assert settings.collection_name == "knowledge_hub"

    def test_base_vector_store_is_abstract(self):
        settings = VectorStoreSettings(provider="test", persist_directory="./tmp")
        with pytest.raises(TypeError):
            BaseVectorStore(settings)

    def test_upsert_contract_accepts_records(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp")
        )
        records = [
            VectorRecord(
                id="chunk_1",
                vector=[0.1, 0.2, 0.3],
                text="First chunk",
                metadata={"source": "doc_a.md"},
            ),
            VectorRecord(
                id="chunk_2",
                vector=[0.3, 0.2, 0.1],
                text="Second chunk",
                metadata={"source": "doc_b.md"},
            ),
        ]

        store.upsert(records)

        assert len(store.records) == 2
        assert store.records["chunk_1"].text == "First chunk"
        assert store.records["chunk_2"].metadata["source"] == "doc_b.md"

    def test_query_contract_returns_normalized_shape(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp")
        )
        store.upsert(
            [
                VectorRecord(
                    id="alpha",
                    vector=[1.0, 0.0],
                    text="alpha text",
                    metadata={"collection": "a"},
                ),
                VectorRecord(
                    id="beta",
                    vector=[0.0, 1.0],
                    text="beta text",
                    metadata={"collection": "b"},
                ),
            ]
        )

        results = store.query(vector=[1.0, 0.0], top_k=1, filters={"collection": "a"})

        assert len(results) == 1
        result = results[0]
        assert isinstance(result, QueryResult)
        assert result.id == "alpha"
        assert isinstance(result.score, float)
        assert result.text == "alpha text"
        assert result.metadata["collection"] == "a"

    def test_get_by_ids_returns_text_and_metadata(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp")
        )
        store.upsert(
            [
                VectorRecord(
                    id="alpha",
                    vector=[1.0, 0.0],
                    text="alpha text",
                    metadata={"collection": "a"},
                )
            ]
        )

        records = store.get_by_ids(["alpha", "missing"])
        assert records == [
            {"id": "alpha", "text": "alpha text", "metadata": {"collection": "a"}}
        ]

    def test_factory_create_with_registered_provider(self):
        VectorStoreFactory.register_provider("fake", FakeVectorStore)
        settings = VectorStoreSettings(provider="fake", persist_directory="./tmp")

        store = VectorStoreFactory.create(settings)

        assert isinstance(store, FakeVectorStore)
        assert store.settings.provider == "fake"

    def test_factory_list_providers(self):
        VectorStoreFactory.register_provider("another_fake", FakeVectorStore)
        providers = VectorStoreFactory.list_providers()

        assert "fake" in providers
        assert "another_fake" in providers

    def test_factory_invalid_provider_raises_error(self):
        settings = VectorStoreSettings(provider="unknown", persist_directory="./tmp")
        with pytest.raises(ValueError, match="Unsupported vector store provider"):
            VectorStoreFactory.create(settings)

    # -- delete_by_metadata contract (I4) --

    def test_delete_by_metadata_removes_matching_records(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp", collection_name="hub")
        )
        store.upsert([
            VectorRecord(id="a", vector=[1.0], text="a", metadata={"source": "doc1.pdf"}),
            VectorRecord(id="b", vector=[1.0], text="b", metadata={"source": "doc1.pdf"}),
            VectorRecord(id="c", vector=[1.0], text="c", metadata={"source": "doc2.pdf"}),
        ])
        deleted = store.delete_by_metadata({"source": "doc1.pdf"})
        assert deleted == 2
        assert len(store.records) == 1
        assert "c" in store.records

    def test_delete_by_metadata_empty_filters_returns_zero(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp")
        )
        store.upsert([VectorRecord(id="x", vector=[1.0], text="x", metadata={})])
        deleted = store.delete_by_metadata({})
        assert deleted == 0
        assert len(store.records) == 1

    def test_delete_by_metadata_no_match_returns_zero(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp")
        )
        store.upsert([VectorRecord(id="x", vector=[1.0], text="x", metadata={"k": "v"})])
        deleted = store.delete_by_metadata({"k": "not_found"})
        assert deleted == 0
        assert len(store.records) == 1

    # -- get_by_metadata contract (I4) --

    def test_get_by_metadata_filters_by_key_value(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp")
        )
        store.upsert([
            VectorRecord(id="a", vector=[1.0], text="a", metadata={"source": "s1"}),
            VectorRecord(id="b", vector=[1.0], text="b", metadata={"source": "s2"}),
        ])
        results = store.get_by_metadata({"source": "s1"})
        assert len(results) == 1
        assert results[0]["id"] == "a"

    # -- get_collection_stats contract (I4) --

    def test_get_collection_stats_returns_entry_count(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp", collection_name="hub")
        )
        store.upsert([
            VectorRecord(id="a", vector=[1.0], text="t", metadata={}),
            VectorRecord(id="b", vector=[1.0], text="t", metadata={}),
        ])
        stats = store.get_collection_stats()
        assert stats["entry_count"] == 2
        assert stats["collection_name"] == "hub"

    # -- get_all_collections contract (I4) --

    def test_get_all_collections_returns_collection_name(self):
        store = FakeVectorStore(
            VectorStoreSettings(provider="fake", persist_directory="./tmp", collection_name="my_col")
        )
        cols = store.get_all_collections()
        assert "my_col" in cols
