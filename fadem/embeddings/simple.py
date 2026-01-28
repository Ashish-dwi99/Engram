import hashlib
import math
from typing import List, Optional

from fadem.embeddings.base import BaseEmbedder


class SimpleEmbedder(BaseEmbedder):
    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)
        self.dims = int(self.config.get("embedding_dims", 1536))

    def embed(self, text: str, memory_action: Optional[str] = None) -> List[float]:
        tokens = [t for t in text.lower().split() if t]
        if not tokens:
            return [0.0] * self.dims

        vector = [0.0] * self.dims
        for token in tokens:
            digest = hashlib.sha256(token.encode()).hexdigest()
            idx = int(digest, 16) % self.dims
            vector[idx] += 1.0

        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector
