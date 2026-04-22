from typing import Dict, Any, List
from openai import AzureOpenAI
from .base_llm import BaseLLM, LLMSettings


class AzureLLM(BaseLLM):
    def __init__(self, settings: LLMSettings):
        super().__init__(settings)
        self.client = AzureOpenAI(
            api_key=settings.api_key,
            azure_endpoint=settings.azure_endpoint,
            api_version=settings.api_version
        )

    def generate(self, prompt: str, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.deployment_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
            **kwargs
        )
        return response.choices[0].message.content

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.settings.deployment_name,
            messages=messages,
            temperature=self.settings.temperature,
            max_tokens=self.settings.max_tokens,
            **kwargs
        )
        return response.choices[0].message.content