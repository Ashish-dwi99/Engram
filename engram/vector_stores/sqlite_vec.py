"""
sqlite-vec vector store implementation.

Uses sqlite-vec extension for vector similarity search with cosine distance.
Enables concurrent multi-agent access from a single SQLite database (unlike
Qdrant local which locks the directory).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import struct
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from engram.memory.utils import matches_filters
from engram.vector_stores.base import VectorStoreBase

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    id: str
    score: float = 0.0
    payload: Dict[str, Any] = None


def _serialize_float32(vector: List[float]) -> bytes:
    """Serialize a float vector to bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


def _deserialize_float32(data: bytes, dims: int) -> List[float]:
    """Deserialize bytes back to a float vector."""
    return list(struct.unpack(f"{dims}f", data))


class SqliteVecStore(VectorStoreBase):
    """Vector store backed by sqlite-vec extension."""

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
        db_path = config.get(
            "path",
            os.path.join(os.path.expanduser("~"), ".engram", "sqlite_vec.db"),
        )
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()

        # Load sqlite-vec extension
        self._conn.enable_load_extension(True)
        import sqlite_vec
        sqlite_vec.load(self._conn)
        self._conn.enable_load_extension(False)

        self._ensure_collection(self.collection_name, self.vector_size)

    def _vec_table(self, name: str) -> str:
        return f"vec_{name}"

    def _payload_table(self, name: str) -> str:
        return f"payload_{name}"

    def _ensure_collection(self, name: str, vector_size: int) -> None:
        """Create vec0 virtual table and payload table if they don't exist."""
        vec_table = self._vec_table(name)
        payload_table = self._payload_table(name)

        with self._lock:
            # Check if collection already exists
            existing = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (payload_table,),
            ).fetchone()

            if not existing:
                self._conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS [{vec_table}] "
                    f"USING vec0(embedding float[{vector_size}] distance_metric=cosine)"
                )
                self._conn.execute(
                    f"""CREATE TABLE IF NOT EXISTS [{payload_table}] (
                        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                        uuid TEXT UNIQUE NOT NULL,
                        payload TEXT DEFAULT '{{}}'
                    )"""
                )
                self._conn.execute(
                    f"CREATE INDEX IF NOT EXISTS [idx_{name}_uuid] ON [{payload_table}](uuid)"
                )
                self._conn.commit()

    def create_col(self, name: str, vector_size: int, distance: str = "cosine") -> None:
        self._ensure_collection(name, vector_size)

    def insert(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> None:
        payloads = payloads or [{} for _ in vectors]
        if len(payloads) != len(vectors):
            raise ValueError("payloads length must match vectors length")
        if ids is not None and len(ids) != len(vectors):
            raise ValueError("ids length must match vectors length")
        ids = ids or [str(uuid.uuid4()) for _ in vectors]

        vec_table = self._vec_table(self.collection_name)
        payload_table = self._payload_table(self.collection_name)

        with self._lock:
            for vector_id, vector, payload in zip(ids, vectors, payloads):
                # Check if uuid already exists (upsert)
                existing = self._conn.execute(
                    f"SELECT rowid FROM [{payload_table}] WHERE uuid = ?",
                    (vector_id,),
                ).fetchone()

                if existing:
                    rowid = existing["rowid"]
                    self._conn.execute(
                        f"UPDATE [{payload_table}] SET payload = ? WHERE rowid = ?",
                        (json.dumps(payload, default=str), rowid),
                    )
                    self._conn.execute(
                        f"UPDATE [{vec_table}] SET embedding = ? WHERE rowid = ?",
                        (_serialize_float32(vector), rowid),
                    )
                else:
                    cursor = self._conn.execute(
                        f"INSERT INTO [{payload_table}] (uuid, payload) VALUES (?, ?)",
                        (vector_id, json.dumps(payload, default=str)),
                    )
                    rowid = cursor.lastrowid
                    self._conn.execute(
                        f"INSERT INTO [{vec_table}] (rowid, embedding) VALUES (?, ?)",
                        (rowid, _serialize_float32(vector)),
                    )
            self._conn.commit()

    def search(
        self,
        query: Optional[str],
        vectors: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryResult]:
        vec_table = self._vec_table(self.collection_name)
        payload_table = self._payload_table(self.collection_name)

        # Over-fetch when filters are present to compensate for post-filtering
        fetch_limit = limit * 3 if filters else limit

        with self._lock:
            # Check if collection has any rows first
            count = self._conn.execute(
                f"SELECT COUNT(*) as cnt FROM [{payload_table}]"
            ).fetchone()
            if not count or count["cnt"] == 0:
                return []

            # sqlite-vec requires `k = ?` in WHERE clause for KNN queries
            rows = self._conn.execute(
                f"""SELECT v.rowid, v.distance
                    FROM [{vec_table}] v
                    WHERE v.embedding MATCH ? AND k = ?""",
                (_serialize_float32(vectors), fetch_limit),
            ).fetchall()

            # Join with payload table in a second step
            results_raw = []
            for row in rows:
                p = self._conn.execute(
                    f"SELECT uuid, payload FROM [{payload_table}] WHERE rowid = ?",
                    (row["rowid"],),
                ).fetchone()
                if p:
                    results_raw.append({
                        "distance": row["distance"],
                        "uuid": p["uuid"],
                        "payload": p["payload"],
                    })

        results = []
        for item in results_raw:
            payload = {}
            try:
                payload = json.loads(item["payload"]) if item["payload"] else {}
            except (json.JSONDecodeError, TypeError):
                pass

            if filters and not matches_filters(payload, filters):
                continue

            # sqlite-vec cosine distance is 0..2 (0=identical).
            # Convert to similarity score: 1 - (distance / 2)
            distance = float(item["distance"])
            score = 1.0 - (distance / 2.0)

            results.append(MemoryResult(
                id=item["uuid"],
                score=score,
                payload=payload,
            ))

        return results[:limit]

    def delete(self, vector_id: str) -> None:
        payload_table = self._payload_table(self.collection_name)
        vec_table = self._vec_table(self.collection_name)

        with self._lock:
            row = self._conn.execute(
                f"SELECT rowid FROM [{payload_table}] WHERE uuid = ?",
                (vector_id,),
            ).fetchone()
            if row:
                rowid = row["rowid"]
                self._conn.execute(
                    f"DELETE FROM [{vec_table}] WHERE rowid = ?", (rowid,)
                )
                self._conn.execute(
                    f"DELETE FROM [{payload_table}] WHERE rowid = ?", (rowid,)
                )
                self._conn.commit()

    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload_table = self._payload_table(self.collection_name)
        vec_table = self._vec_table(self.collection_name)

        with self._lock:
            row = self._conn.execute(
                f"SELECT rowid FROM [{payload_table}] WHERE uuid = ?",
                (vector_id,),
            ).fetchone()
            if not row:
                return
            rowid = row["rowid"]

            if vector is not None:
                self._conn.execute(
                    f"UPDATE [{vec_table}] SET embedding = ? WHERE rowid = ?",
                    (_serialize_float32(vector), rowid),
                )
            if payload is not None:
                self._conn.execute(
                    f"UPDATE [{payload_table}] SET payload = ? WHERE rowid = ?",
                    (json.dumps(payload, default=str), rowid),
                )
            self._conn.commit()

    def get(self, vector_id: str) -> Optional[MemoryResult]:
        payload_table = self._payload_table(self.collection_name)

        with self._lock:
            row = self._conn.execute(
                f"SELECT uuid, payload FROM [{payload_table}] WHERE uuid = ?",
                (vector_id,),
            ).fetchone()

        if not row:
            return None

        payload = {}
        try:
            payload = json.loads(row["payload"]) if row["payload"] else {}
        except (json.JSONDecodeError, TypeError):
            pass

        return MemoryResult(id=row["uuid"], score=0.0, payload=payload)

    def list_cols(self) -> List[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'payload_%'",
            ).fetchall()
        return [row["name"].replace("payload_", "", 1) for row in rows]

    def delete_col(self) -> None:
        vec_table = self._vec_table(self.collection_name)
        payload_table = self._payload_table(self.collection_name)

        with self._lock:
            self._conn.execute(f"DROP TABLE IF EXISTS [{vec_table}]")
            self._conn.execute(f"DROP TABLE IF EXISTS [{payload_table}]")
            self._conn.commit()

    def col_info(self) -> Dict[str, Any]:
        payload_table = self._payload_table(self.collection_name)

        with self._lock:
            row = self._conn.execute(
                f"SELECT COUNT(*) as cnt FROM [{payload_table}]",
            ).fetchone()

        count = row["cnt"] if row else 0
        return {
            "name": self.collection_name,
            "points": count,
            "vector_size": self.vector_size,
        }

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[MemoryResult]:
        payload_table = self._payload_table(self.collection_name)
        effective_limit = limit or 100

        with self._lock:
            rows = self._conn.execute(
                f"SELECT uuid, payload FROM [{payload_table}] LIMIT ?",
                (effective_limit * 3 if filters else effective_limit,),
            ).fetchall()

        results = []
        for row in rows:
            payload = {}
            try:
                payload = json.loads(row["payload"]) if row["payload"] else {}
            except (json.JSONDecodeError, TypeError):
                pass

            if filters and not matches_filters(payload, filters):
                continue

            results.append(MemoryResult(id=row["uuid"], score=0.0, payload=payload))

        return results[:effective_limit]

    def reset(self) -> None:
        self.delete_col()
        self._ensure_collection(self.collection_name, self.vector_size)
