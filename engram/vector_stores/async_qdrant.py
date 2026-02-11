"""Async Qdrant vector store implementation.

Uses the async Qdrant client for native async operations.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from engram.vector_stores.base import MemoryResult

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams, Filter, FieldCondition, MatchValue
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False


class AsyncQdrantVectorStore:
    """Async Qdrant vector store for Engram memories."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        if not HAS_QDRANT:
            raise ImportError("qdrant-client is required. Install with: pip install qdrant-client")

        config = config or {}
        self.config = config
        self.collection_name = config.get("collection_name", "engram_memories")
        self.vector_size = (
            config.get("embedding_model_dims")
            or config.get("vector_size")
            or config.get("embedding_dims")
            or 1536
        )
        self.distance = config.get("distance", "cosine")

        # Create async client
        self.client = self._create_client(config)
        self._initialized = False

    def _create_client(self, config: Dict[str, Any]) -> "AsyncQdrantClient":
        """Create an async Qdrant client."""
        url = config.get("url")
        api_key = config.get("api_key")
        path = config.get("path")
        host = config.get("host")
        port = config.get("port", 6333)

        if url:
            return AsyncQdrantClient(url=url, api_key=api_key)
        elif path:
            return AsyncQdrantClient(path=path)
        elif host:
            return AsyncQdrantClient(host=host, port=port, api_key=api_key)
        else:
            # Default to in-memory
            return AsyncQdrantClient(location=":memory:")

    async def initialize(self) -> None:
        """Initialize the collection if needed."""
        if self._initialized:
            return

        exists = await self.client.collection_exists(self.collection_name)

        if exists:
            # Check dimensions match
            info = await self.client.get_collection(self.collection_name)
            vectors_config = info.config.params.vectors
            existing_size = None
            if hasattr(vectors_config, 'size'):
                existing_size = vectors_config.size
            elif isinstance(vectors_config, dict) and '' in vectors_config:
                existing_size = vectors_config[''].size

            if existing_size and existing_size != self.vector_size:
                # Dimension mismatch - recreate
                await self.client.delete_collection(self.collection_name)
                await self._create_collection()
        else:
            await self._create_collection()

        self._initialized = True

    async def _create_collection(self) -> None:
        """Create the vector collection."""
        distance_map = {
            "cosine": Distance.COSINE,
            "dot": Distance.DOT,
            "euclid": Distance.EUCLID,
        }
        dist = distance_map.get(self.distance, Distance.COSINE)

        await self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=dist),
        )

    async def insert(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> None:
        """Insert vectors into the collection."""
        await self.initialize()

        payloads = payloads or [{} for _ in vectors]
        if len(payloads) != len(vectors):
            raise ValueError("payloads length must match vectors length")

        ids = ids or [str(uuid.uuid4()) for _ in vectors]
        if len(ids) != len(vectors):
            raise ValueError("ids length must match vectors length")

        points = [
            PointStruct(id=pid, vector=vec, payload=payload)
            for pid, vec, payload in zip(ids, vectors, payloads)
        ]

        await self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    async def search(
        self,
        query_vector: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryResult]:
        """Search for similar vectors."""
        await self.initialize()

        # Build filter
        qdrant_filter = None
        if filters:
            conditions = []
            for key, value in filters.items():
                if value is not None:
                    conditions.append(
                        FieldCondition(key=key, match=MatchValue(value=value))
                    )
            if conditions:
                qdrant_filter = Filter(must=conditions)

        response = await self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            MemoryResult(
                id=str(r.id),
                score=float(r.score or 0.0),
                payload=r.payload or {},
            )
            for r in response.points
        ]

    async def delete(self, ids: List[str]) -> None:
        """Delete vectors by ID."""
        await self.initialize()

        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=ids,
        )

    async def get(self, ids: List[str]) -> List[Dict[str, Any]]:
        """Get vectors by ID."""
        await self.initialize()

        results = await self.client.retrieve(
            collection_name=self.collection_name,
            ids=ids,
            with_payload=True,
            with_vectors=True,
        )

        return [
            {
                "id": str(r.id),
                "vector": r.vector,
                "payload": r.payload or {},
            }
            for r in results
        ]

    async def count(self) -> int:
        """Get the number of vectors in the collection."""
        await self.initialize()

        info = await self.client.get_collection(self.collection_name)
        return info.points_count

    async def close(self) -> None:
        """Close the client connection."""
        await self.client.close()
