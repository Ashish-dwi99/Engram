from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fadem.memory.utils import matches_filters
from fadem.vector_stores.base import VectorStoreBase


@dataclass
class MemoryResult:
    id: str
    score: float = 0.0
    payload: Dict[str, Any] = None


class InMemoryVectorStore(VectorStoreBase):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.collection_name = self.config.get("collection_name", "fadem_memories")
        self.vector_size = self.config.get("embedding_model_dims")
        self._store: Dict[str, Dict[str, Any]] = {}

    def create_col(self, name: str, vector_size: int, distance: str = "cosine") -> None:
        self.collection_name = name
        self.vector_size = vector_size

    def insert(self, vectors: List[List[float]], payloads: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None) -> None:
        payloads = payloads or [{} for _ in vectors]
        ids = ids or [str(uuid.uuid4()) for _ in vectors]
        for vector_id, vector, payload in zip(ids, vectors, payloads):
            self._store[vector_id] = {"vector": vector, "payload": payload}

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def search(self, query: Optional[str], vectors: List[float], limit: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[MemoryResult]:
        results: List[MemoryResult] = []
        for vector_id, record in self._store.items():
            payload = record.get("payload", {})
            if filters and not matches_filters(payload, filters):
                continue
            score = self._cosine_similarity(vectors, record.get("vector", []))
            results.append(MemoryResult(id=vector_id, score=score, payload=payload))

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]

    def delete(self, vector_id: str) -> None:
        if vector_id in self._store:
            del self._store[vector_id]

    def update(self, vector_id: str, vector: Optional[List[float]] = None, payload: Optional[Dict[str, Any]] = None) -> None:
        if vector_id not in self._store:
            return
        if vector is not None:
            self._store[vector_id]["vector"] = vector
        if payload is not None:
            self._store[vector_id]["payload"] = payload

    def get(self, vector_id: str) -> Optional[MemoryResult]:
        record = self._store.get(vector_id)
        if not record:
            return None
        return MemoryResult(id=vector_id, score=0.0, payload=record.get("payload", {}))

    def list_cols(self) -> List[str]:
        return [self.collection_name]

    def delete_col(self) -> None:
        self._store = {}

    def col_info(self) -> Dict[str, Any]:
        return {"name": self.collection_name, "size": len(self._store), "vector_size": self.vector_size}

    def list(self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[MemoryResult]:
        results: List[MemoryResult] = []
        for vector_id, record in self._store.items():
            payload = record.get("payload", {})
            if filters and not matches_filters(payload, filters):
                continue
            results.append(MemoryResult(id=vector_id, score=0.0, payload=payload))
        if limit is not None:
            results = results[:limit]
        return results

    def reset(self) -> None:
        self._store = {}
