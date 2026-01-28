from typing import List, Optional

from fadem.embeddings.base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        try:
            from openai import OpenAI
        except Exception as exc:
            raise ImportError("openai package is required for OpenAIEmbedder") from exc
        self.client = OpenAI()
        self.model = self.config.get("model", "text-embedding-3-small")

    def embed(self, text: str, memory_action: Optional[str] = None) -> List[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding
