import base64
import os
from typing import List, Optional, Union
from openai import AzureOpenAI
from ..base_vision_llm import BaseVisionLLM, VisionLLMSettings


def encode_image(image_path_or_bytes: Union[str, bytes]) -> str:
    if isinstance(image_path_or_bytes, str):
        with open(image_path_or_bytes, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    return base64.b64encode(image_path_or_bytes).decode('utf-8')


class AzureVisionLLM(BaseVisionLLM):
    def __init__(self, settings: VisionLLMSettings):
        super().__init__(settings)
        self.client = AzureOpenAI(
            api_key=settings.api_key,
            azure_endpoint=settings.azure_endpoint,
            api_version=settings.api_version
        )

    def describe_image(self, image_path: str, prompt: str = None) -> str:
        return self.chat_with_image(prompt or "Describe this image in detail.", image_path)

    def chat_with_image(
        self,
        text: str,
        image_path: Optional[Union[str, bytes]] = None,
        **kwargs
    ) -> str:
        content = [{"type": "text", "text": text}]
        
        if image_path:
            base64_image = encode_image(image_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
            })
            
        messages = [
            {
                "role": "user",
                "content": content
            }
        ]
        
        response = self.client.chat.completions.create(
            model=self.settings.deployment_name,
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 500),
            **{k: v for k, v in kwargs.items() if k != "max_tokens"}
        )
        return response.choices[0].message.content
