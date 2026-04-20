import base64
from typing import List
from openai import AzureOpenAI
from . import BaseVisionLLM, VisionLLMSettings


def encode_image(image_path: str) -> str:
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


class AzureVisionLLM(BaseVisionLLM):
    def __init__(self, settings: VisionLLMSettings):
        super().__init__(settings)
        self.client = AzureOpenAI(
            api_key=settings.api_key,
            azure_endpoint=settings.azure_endpoint,
            api_version=settings.api_version
        )

    def describe_image(self, image_path: str, prompt: str = None) -> str:
        base64_image = encode_image(image_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt or "Describe this image in detail."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }
        ]
        response = self.client.chat.completions.create(
            model=self.settings.deployment_name,
            messages=messages,
            max_tokens=500
        )
        return response.choices[0].message.content

    def describe_images(self, image_paths: List[str], prompt: str = None) -> List[str]:
        return [self.describe_image(path, prompt) for path in image_paths]