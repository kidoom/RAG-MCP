from typing import Dict, Any, List
from openai import OpenAI
from . import BaseLLM, LLMSettings


class OpenAILLM(BaseLLM):
    def __init__(self, settings: LLMSettings):
        super().__init__(settings)
        self.client = OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url
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