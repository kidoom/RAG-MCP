import uuid

import pytest

from src.libs.vector_store import VectorRecord, VectorStoreFactory, VectorStoreSettings


@pytest.mark.integration
class TestChromaStoreRoundtrip:
    def test_factory_can_create_chroma_store(self, tmp_path):
        settings = VectorStoreSettings(
            provider="chroma",
            persist_directory=str(tmp_path / "chroma"),
            collection_name="factory_create_test",
        )

        store = VectorStoreFactory.create(settings)

        assert store.settings.provider == "chroma"

    def test_upsert_query_roundtrip_with_top_k_and_filters(self, tmp_path):
        collection_name = f"roundtrip_{uuid.uuid4().hex[:8]}"
        settings = VectorStoreSettings(
            provider="chroma",
            persist_directory=str(tmp_path / "chroma"),
            collection_name=collection_name,
        )
        store = VectorStoreFactory.create(settings)

        records = [
            VectorRecord(
                id="chunk_alpha",
                vector=[1.0, 0.0, 0.0],
                text="alpha content",
                metadata={"source": "doc_a.md", "topic": "alpha"},
            ),
            VectorRecord(
                id="chunk_beta",
                vector=[0.9, 0.1, 0.0],
                text="beta content",
                metadata={"source": "doc_b.md", "topic": "beta"},
            ),
            VectorRecord(
                id="chunk_gamma",
                vector=[0.0, 1.0, 0.0],
                text="gamma content",
                metadata={"source": "doc_c.md", "topic": "alpha"},
            ),
        ]
        store.upsert(records)

        top_two = store.query(vector=[1.0, 0.0, 0.0], top_k=2)
        assert len(top_two) == 2
        assert top_two[0].id == "chunk_alpha"
        assert top_two[0].text == "alpha content"
        assert isinstance(top_two[0].score, float)

        filtered = store.query(
            vector=[1.0, 0.0, 0.0],
            top_k=5,
            filters={"topic": "beta"},
        )
        assert len(filtered) == 1
        assert filtered[0].id == "chunk_beta"
        assert filtered[0].metadata["topic"] == "beta"

    def test_persistence_across_store_instances(self, tmp_path):
        persist_dir = tmp_path / "persisted_chroma"
        collection_name = f"persist_{uuid.uuid4().hex[:8]}"
        settings = VectorStoreSettings(
            provider="chroma",
            persist_directory=str(persist_dir),
            collection_name=collection_name,
        )

        writer = VectorStoreFactory.create(settings)
        writer.upsert(
            [
                VectorRecord(
                    id="persisted_chunk",
                    vector=[0.2, 0.8],
                    text="persisted content",
                    metadata={"source": "persisted_doc.md", "topic": "persist"},
                )
            ]
        )

        reader = VectorStoreFactory.create(settings)
        results = reader.query(vector=[0.2, 0.8], top_k=1)

        assert len(results) == 1
        assert results[0].id == "persisted_chunk"
        assert results[0].text == "persisted content"
