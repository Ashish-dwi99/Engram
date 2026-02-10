import os
from typing import List, Optional

from engram.embeddings.base import BaseEmbedder


class NvidiaEmbedder(BaseEmbedder):
    """Embedding provider for NVIDIA API (OpenAI-compatible). Default model: nv-embedqa-e5-v5."""

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        try:
            from openai import OpenAI
        except Exception as exc:
            raise ImportError("openai package is required for NvidiaEmbedder") from exc

        api_key = self.config.get("api_key") or "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"
        if not api_key:
            raise ValueError(
                "NVIDIA API key required. Set config['api_key'] or NVIDIA_API_KEY env var."
            )

        base_url = self.config.get("base_url", "https://integrate.api.nvidia.com/v1")
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = self.config.get("model", "nvidia/nv-embedqa-e5-v5")

    def embed(self, text: str, memory_action: Optional[str] = None) -> List[float]:
        # NVIDIA embedding models distinguish between passage and query input types
        if memory_action in ("search", "forget"):
            input_type = "query"
        else:
            input_type = "passage"

        response = self.client.embeddings.create(
            input=[text],
            model=self.model,
            encoding_format="float",
            extra_body={"input_type": input_type, "truncate": "NONE"},
        )
        return response.data[0].embedding
