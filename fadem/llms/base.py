from abc import ABC, abstractmethod
from typing import Optional


class BaseLLM(ABC):
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    @abstractmethod
    def generate(self, prompt: str) -> str:
        pass
