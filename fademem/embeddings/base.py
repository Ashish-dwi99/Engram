from abc import ABC, abstractmethod
from typing import Optional


class BaseEmbedder(ABC):
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def embed(self, text: str, memory_action: Optional[str] = None):
        pass
