from typing import Dict, Any, List
from openai import OpenAI
from . import BaseLLM, LLMSettings


class OllamaLLM(BaseLLM):
    def __init__(self, settings: LLMSettings):
        super().__init__(settings)
        self.client = OpenAI(
            base_url=settings.base_url or "http://localhost:11434/v1",
            api_key="ollama"  # Ollama doesn't need API key
        )

    def generate(self, prompt: str, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
            **kwargs
        )
        return response.choices[0].message.content

    def generate_with_messages(self, messages: List[Dict[str, str]], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=messages,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
            **kwargs
        )
        return response.choices[0].message.content