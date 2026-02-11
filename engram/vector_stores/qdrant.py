from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from engram.vector_stores.base import MemoryResult, VectorStoreBase


class QdrantVectorStore(VectorStoreBase):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        self.config = config
        self.collection_name = config.get("collection_name", "fadem_memories")
        self.vector_size = (
            config.get("embedding_model_dims")
            or config.get("vector_size")
            or config.get("embedding_dims")
            or 1536
        )
        self.distance = config.get("distance", "cosine")

        self.client = _create_client(config)

        if self.client.collection_exists(self.collection_name):
            # Check if existing collection has correct dimensions
            existing_size = self._get_collection_vector_size()
            if existing_size is not None and existing_size != self.vector_size:
                # Dimension mismatch - recreate collection
                self.client.delete_collection(self.collection_name)
                self.create_col(self.collection_name, self.vector_size, self.distance)
        else:
            self.create_col(self.collection_name, self.vector_size, self.distance)

    def _get_collection_vector_size(self) -> Optional[int]:
        """Get the vector size of an existing collection."""
        try:
            info = self.client.get_collection(self.collection_name)
            # Handle different Qdrant client versions
            vectors_config = info.config.params.vectors
            if hasattr(vectors_config, 'size'):
                return vectors_config.size
            elif isinstance(vectors_config, dict) and '' in vectors_config:
                return vectors_config[''].size
            return None
        except Exception:
            return None

    def create_col(self, name: str, vector_size: int, distance: str = "cosine") -> None:
        from qdrant_client.models import Distance, VectorParams

        distance_map = {
            "cosine": Distance.COSINE,
            "dot": Distance.DOT,
            "euclid": Distance.EUCLID,
        }
        dist = distance_map.get(distance, Distance.COSINE)
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=vector_size, distance=dist),
        )

    def insert(self, vectors: List[List[float]], payloads: Optional[List[Dict[str, Any]]] = None, ids: Optional[List[str]] = None) -> None:
        from qdrant_client.models import PointStruct

        payloads = payloads or [{} for _ in vectors]
        if len(payloads) != len(vectors):
            raise ValueError("payloads length must match vectors length")
        if ids is not None and len(ids) != len(vectors):
            raise ValueError("ids length must match vectors length")
        ids = ids or [str(uuid.uuid4()) for _ in vectors]
        points = [PointStruct(id=pid, vector=vec, payload=payload) for pid, vec, payload in zip(ids, vectors, payloads)]
        self.client.upsert(collection_name=self.collection_name, points=points)

    def search(self, query: Optional[str], vectors: List[float], limit: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[MemoryResult]:
        qdrant_filter = _build_qdrant_filter(filters)
        # Use query_points (new API) instead of deprecated search method
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=vectors,
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        return [MemoryResult(id=str(r.id), score=float(r.score or 0.0), payload=r.payload or {}) for r in response.points]

    def delete(self, vector_id: str) -> None:
        from qdrant_client.models import PointIdsList

        selector = PointIdsList(points=[vector_id])
        self.client.delete(collection_name=self.collection_name, points_selector=selector)

    def update(self, vector_id: str, vector: Optional[List[float]] = None, payload: Optional[Dict[str, Any]] = None) -> None:
        if vector is not None:
            from qdrant_client.models import PointStruct

            # Preserve existing payload when only updating the vector
            if payload is None:
                existing = self.get(vector_id)
                payload = existing.payload if existing else {}
            point = PointStruct(id=vector_id, vector=vector, payload=payload)
            self.client.upsert(collection_name=self.collection_name, points=[point])
            return

        if payload is not None:
            self.client.set_payload(collection_name=self.collection_name, payload=payload, points=[vector_id])

    def get(self, vector_id: str) -> Optional[MemoryResult]:
        results = self.client.retrieve(collection_name=self.collection_name, ids=[vector_id], with_payload=True)
        if not results:
            return None
        res = results[0]
        return MemoryResult(id=str(res.id), score=0.0, payload=res.payload or {})

    def list_cols(self) -> List[str]:
        collections = self.client.get_collections()
        return [c.name for c in collections.collections]

    def delete_col(self) -> None:
        self.client.delete_collection(collection_name=self.collection_name)

    def col_info(self) -> Dict[str, Any]:
        info = self.client.get_collection(self.collection_name)
        return {"name": self.collection_name, "points": info.points_count, "vector_size": self.vector_size}

    def list(self, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[MemoryResult]:
        qdrant_filter = _build_qdrant_filter(filters)
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=qdrant_filter,
            with_payload=True,
            limit=limit or 100,
        )
        return [MemoryResult(id=str(p.id), score=0.0, payload=p.payload or {}) for p in points]

    def reset(self) -> None:
        self.delete_col()
        self.create_col(self.collection_name, self.vector_size, self.distance)

    def close(self) -> None:
        """Close the Qdrant client connection."""
        if hasattr(self, 'client') and self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass


def _create_client(config: Dict[str, Any]):
    from qdrant_client import QdrantClient

    path = config.get("path")
    url = config.get("url")
    host = config.get("host")
    port = config.get("port", 6333)
    api_key = config.get("api_key")

    if path:
        return QdrantClient(path=path)
    if url:
        return QdrantClient(url=url, api_key=api_key)
    return QdrantClient(host=host or "localhost", port=port, api_key=api_key)


def _build_qdrant_filter(filters: Optional[Dict[str, Any]]):
    if not filters:
        return None

    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchText, MatchValue, Range

    must = []
    must_not = []
    should = []

    def add_condition(key: str, condition: Any):
        if condition == "*":
            return
        if not isinstance(condition, dict):
            must.append(FieldCondition(key=key, match=MatchValue(value=condition)))
            return

        for operator, value in condition.items():
            if operator == "eq":
                must.append(FieldCondition(key=key, match=MatchValue(value=value)))
            elif operator == "ne":
                must_not.append(FieldCondition(key=key, match=MatchValue(value=value)))
            elif operator == "in":
                must.append(FieldCondition(key=key, match=MatchAny(any=value)))
            elif operator == "nin":
                must_not.append(FieldCondition(key=key, match=MatchAny(any=value)))
            elif operator in {"gt", "gte", "lt", "lte"}:
                range_kwargs = {}
                if operator == "gt":
                    range_kwargs["gt"] = value
                if operator == "gte":
                    range_kwargs["gte"] = value
                if operator == "lt":
                    range_kwargs["lt"] = value
                if operator == "lte":
                    range_kwargs["lte"] = value
                must.append(FieldCondition(key=key, range=Range(**range_kwargs)))
            elif operator in {"contains", "icontains"}:
                must.append(FieldCondition(key=key, match=MatchText(text=str(value))))

    for key, condition in filters.items():
        if key == "AND" and isinstance(condition, list):
            for sub in condition:
                for sub_key, sub_cond in sub.items():
                    add_condition(sub_key, sub_cond)
            continue
        if key == "OR" and isinstance(condition, list):
            for sub in condition:
                for sub_key, sub_cond in sub.items():
                    if isinstance(sub_cond, dict) and "eq" in sub_cond:
                        should.append(FieldCondition(key=sub_key, match=MatchValue(value=sub_cond["eq"])))
                    elif not isinstance(sub_cond, dict):
                        should.append(FieldCondition(key=sub_key, match=MatchValue(value=sub_cond)))
            continue
        if key == "NOT" and isinstance(condition, list):
            for sub in condition:
                for sub_key, sub_cond in sub.items():
                    if isinstance(sub_cond, dict) and "eq" in sub_cond:
                        must_not.append(FieldCondition(key=sub_key, match=MatchValue(value=sub_cond["eq"])))
                    elif not isinstance(sub_cond, dict):
                        must_not.append(FieldCondition(key=sub_key, match=MatchValue(value=sub_cond)))
            continue
        add_condition(key, condition)

    if not (must or must_not or should):
        return None
    return Filter(must=must or None, must_not=must_not or None, should=should or None)
