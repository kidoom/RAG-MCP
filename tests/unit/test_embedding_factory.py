import pytest
from unittest.mock import MagicMock, patch
from src.libs.embedding import (
    BaseEmbedding,
    EmbeddingSettings,
    EmbeddingFactory,
    OpenAIEmbedding,
    AzureEmbedding,
    OllamaEmbedding,
)


class TestEmbeddingFactory:
    """Test suite for EmbeddingFactory."""

    def test_factory_create_openai_embedding(self):
        """Test creating OpenAI embedding instance."""
        settings = EmbeddingSettings(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="test-key"
        )
        embedding = EmbeddingFactory.create(settings)
        assert isinstance(embedding, OpenAIEmbedding)
        assert embedding.settings.model == "text-embedding-3-small"
        assert embedding.settings.dimensions == 1536

    def test_factory_create_azure_embedding(self):
        """Test creating Azure embedding instance."""
        settings = EmbeddingSettings(
            provider="azure",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="test-key",
            azure_endpoint="https://test.openai.azure.com/",
            deployment_name="embedding-model",
            api_version="2024-02-15-preview"
        )
        embedding = EmbeddingFactory.create(settings)
        assert isinstance(embedding, AzureEmbedding)
        assert embedding.settings.deployment_name == "embedding-model"

    def test_factory_create_ollama_embedding(self):
        """Test creating Ollama embedding instance."""
        settings = EmbeddingSettings(
            provider="ollama",
            model="nomic-embed-text",
            dimensions=768,
            base_url="http://localhost:11434"
        )
        embedding = EmbeddingFactory.create(settings)
        assert isinstance(embedding, OllamaEmbedding)
        assert embedding.settings.model == "nomic-embed-text"

    def test_factory_create_huggingface_embedding(self):
        """Test creating HuggingFace embedding instance."""
        from src.libs.embedding import HuggingFaceEmbedding
        settings = EmbeddingSettings(
            provider="huggingface",
            model="all-MiniLM-L6-v2",
            dimensions=384
        )
        # Mock SentenceTransformer to avoid downloading model during test
        with patch("src.libs.embedding.huggingface_embedding.SentenceTransformer") as mock_st:
            embedding = EmbeddingFactory.create(settings)
            assert isinstance(embedding, HuggingFaceEmbedding)
            assert embedding.settings.model == "all-MiniLM-L6-v2"

    def test_factory_create_with_case_insensitive_provider(self):
        """Test that provider names are case-insensitive."""
        settings = EmbeddingSettings(
            provider="OPENAI",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="test-key"
        )
        embedding = EmbeddingFactory.create(settings)
        assert isinstance(embedding, OpenAIEmbedding)

    def test_factory_invalid_provider(self):
        """Test that invalid provider raises ValueError."""
        settings = EmbeddingSettings(
            provider="invalid-provider",
            model="test-model",
            dimensions=768
        )
        with pytest.raises(ValueError, match="Unsupported embedding provider"):
            EmbeddingFactory.create(settings)

    def test_factory_list_providers(self):
        """Test listing all available providers."""
        providers = EmbeddingFactory.list_providers()
        assert isinstance(providers, list)
        assert "openai" in providers
        assert "azure" in providers
        assert "ollama" in providers
        assert "qwen" in providers
        assert "gemini" in providers

    def test_factory_register_custom_provider(self):
        """Test registering a custom provider."""
        class CustomEmbedding(BaseEmbedding):
            def embed_texts(self, texts):
                return [[0.1] * self.settings.dimensions for _ in texts]

            def embed_query(self, query):
                return [0.1] * self.settings.dimensions

        EmbeddingFactory.register_provider("custom", CustomEmbedding)
        settings = EmbeddingSettings(
            provider="custom",
            model="custom-model",
            dimensions=128
        )
        embedding = EmbeddingFactory.create(settings)
        assert isinstance(embedding, CustomEmbedding)


class TestBaseEmbeddingInterface:
    """Test suite for BaseEmbedding interface compliance."""

    def test_embedding_settings_creation(self):
        """Test creating EmbeddingSettings dataclass."""
        settings = EmbeddingSettings(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="test-key",
            base_url="https://api.openai.com"
        )
        assert settings.provider == "openai"
        assert settings.model == "text-embedding-3-small"
        assert settings.dimensions == 1536
        assert settings.api_key == "test-key"
        assert settings.base_url == "https://api.openai.com"

    def test_embedding_settings_optional_fields(self):
        """Test EmbeddingSettings with optional fields."""
        settings = EmbeddingSettings(
            provider="ollama",
            model="nomic-embed-text",
            dimensions=768
        )
        assert settings.api_key is None
        assert settings.base_url is None
        assert settings.azure_endpoint is None

    def test_base_embedding_is_abstract(self):
        """Test that BaseEmbedding cannot be instantiated directly."""
        settings = EmbeddingSettings(
            provider="test",
            model="test-model",
            dimensions=768
        )
        with pytest.raises(TypeError):
            BaseEmbedding(settings)

    @patch("src.libs.embedding.openai_embedding.OpenAI")
    def test_openai_embedding_interface(self, mock_openai_class):
        """Test OpenAI embedding implements the interface."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock embed_texts response
        mock_response = MagicMock()
        mock_response.data = [
            MagicMock(embedding=[0.1, 0.2, 0.3]),
            MagicMock(embedding=[0.4, 0.5, 0.6])
        ]
        mock_client.embeddings.create.return_value = mock_response

        settings = EmbeddingSettings(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            api_key="test-key"
        )
        embedding = OpenAIEmbedding(settings)

        # Test embed_texts method
        result = embedding.embed_texts(["text1", "text2"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    @patch("src.libs.embedding.openai_embedding.OpenAI")
    def test_openai_embedding_embed_query(self, mock_openai_class):
        """Test OpenAI embedding embed_query method."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
        mock_client.embeddings.create.return_value = mock_response

        settings = EmbeddingSettings(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3,
            api_key="test-key"
        )
        embedding = OpenAIEmbedding(settings)

        result = embedding.embed_query("test query")
        assert result == [0.1, 0.2, 0.3]

    def test_embedding_factory_integration(self):
        """Test integration between factory and embedding instances."""
        settings = EmbeddingSettings(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=1536,
            api_key="test-key"
        )
        embedding = EmbeddingFactory.create(settings)
        
        # Verify interface methods exist and are callable
        assert hasattr(embedding, "embed_texts")
        assert hasattr(embedding, "embed_query")
        assert callable(embedding.embed_texts)
        assert callable(embedding.embed_query)
        assert hasattr(embedding, "settings")
        assert embedding.settings == settings
