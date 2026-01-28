from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class VectorStoreBase(ABC):
    @abstractmethod
    def create_col(self, name: str, vector_size: int, distance: str = "cosine") -> None:
        pass

    @abstractmethod
    def insert(self, vectors: List[List[float]], payloads: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None) -> None:
        pass

    @abstractmethod
    def search(self, query: Optional[str], vectors: List[float], limit: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Any]:
        pass

    @abstractmethod
    def delete(self, vector_id: str) -> None:
        pass

    @abstractmethod
    def update(self, vector_id: str, vector: Optional[List[float]] = None, payload: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    def get(self, vector_id: str) -> Optional[Any]:
        pass

    @abstractmethod
    def list_cols(self) -> List[str]:
        pass

    @abstractmethod
    def delete_col(self) -> None:
        pass

    @abstractmethod
    def col_info(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def list(self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Any]:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass
