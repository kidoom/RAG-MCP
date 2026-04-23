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
