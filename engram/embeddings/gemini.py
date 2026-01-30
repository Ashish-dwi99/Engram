import os
from typing import List, Optional

from engram.embeddings.base import BaseEmbedder


class GeminiEmbedder(BaseEmbedder):
    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.api_key = self.config.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not provided. Set GEMINI_API_KEY or pass api_key in config.")

        self.model = self.config.get("model", "gemini-embedding-001")

        self._client_type = None
        self._client = None
        self._genai = None

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._client_type = "generativeai"
            self._genai = genai
        except Exception:
            try:
                from google import genai

                self._client_type = "genai"
                self._client = genai.Client(api_key=self.api_key)
            except Exception as exc:
                raise ImportError(
                    "Install google-generativeai or google-genai to use GeminiEmbedder"
                ) from exc

    def embed(self, text: str, memory_action: Optional[str] = None) -> List[float]:
        if self._client_type == "generativeai":
            response = self._genai.embed_content(
                model=self.model,
                content=text,
            )
            embedding = response.get("embedding") if isinstance(response, dict) else getattr(response, "embedding", None)
            return embedding or []

        if self._client_type == "genai":
            response = self._client.models.embed_content(
                model=self.model,
                contents=text,
            )
            return _extract_embedding_from_response(response)

        return []


def _extract_embedding_from_response(response) -> List[float]:
    if response is None:
        return []
    embedding = getattr(response, "embedding", None)
    if embedding:
        return embedding
    embeddings = getattr(response, "embeddings", None)
    if embeddings and isinstance(embeddings, list):
        first = embeddings[0]
        vector = getattr(first, "values", None) or getattr(first, "embedding", None)
        if vector:
            return vector
    return []
