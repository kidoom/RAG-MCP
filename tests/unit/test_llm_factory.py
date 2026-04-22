import pytest
from unittest.mock import MagicMock, patch
from src.libs.llm.base_llm import LLMSettings
from src.libs.llm.base_vision_llm import VisionLLMSettings
from src.libs.llm.llm_factory import LLMFactory
from src.libs.llm.openai_llm import OpenAILLM
from src.libs.llm.vision_llm.openai_vision_llm import OpenAIVisionLLM

def test_llm_factory_create_openai():
    settings = LLMSettings(
        provider="openai",
        model="gpt-4o",
        api_key="test-key"
    )
    llm = LLMFactory.create_llm(settings)
    assert isinstance(llm, OpenAILLM)
    assert llm.settings.model == "gpt-4o"

def test_llm_factory_create_vision_openai():
    settings = VisionLLMSettings(
        provider="openai",
        model="gpt-4o",
        api_key="test-key"
    )
    vision_llm = LLMFactory.create_vision_llm(settings)
    assert isinstance(vision_llm, OpenAIVisionLLM)
    assert vision_llm.settings.model == "gpt-4o"

def test_llm_factory_invalid_provider():
    settings = LLMSettings(
        provider="invalid",
        model="test"
    )
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMFactory.create_llm(settings)

def test_vision_llm_factory_invalid_provider():
    settings = VisionLLMSettings(
        provider="invalid",
        model="test"
    )
    with pytest.raises(ValueError, match="Unsupported Vision LLM provider"):
        LLMFactory.create_vision_llm(settings)

@patch("src.libs.llm.openai_llm.OpenAI")
def test_llm_generate(mock_openai_class):
    mock_client = MagicMock()
    mock_openai_class.return_value = mock_client
    mock_client.chat.completions.create.return_value.choices[0].message.content = "test response"
    
    settings = LLMSettings(
        provider="openai",
        model="gpt-4o",
        api_key="test-key"
    )
    llm = LLMFactory.create_llm(settings)
    response = llm.generate("hello")
    
    assert response == "test response"
    mock_client.chat.completions.create.assert_called_once()
