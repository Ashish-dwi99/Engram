import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


class SQLiteManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    memory TEXT NOT NULL,
                    user_id TEXT,
                    agent_id TEXT,
                    run_id TEXT,
                    app_id TEXT,
                    metadata TEXT DEFAULT '{}',
                    categories TEXT DEFAULT '[]',
                    immutable INTEGER DEFAULT 0,
                    expiration_date TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    layer TEXT DEFAULT 'sml' CHECK (layer IN ('sml', 'lml')),
                    strength REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT DEFAULT CURRENT_TIMESTAMP,
                    embedding TEXT,
                    related_memories TEXT DEFAULT '[]',
                    source_memories TEXT DEFAULT '[]',
                    tombstone INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_user_layer ON memories(user_id, layer);
                CREATE INDEX IF NOT EXISTS idx_strength ON memories(strength DESC);
                CREATE INDEX IF NOT EXISTS idx_tombstone ON memories(tombstone);

                CREATE TABLE IF NOT EXISTS memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    memory_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    old_strength REAL,
                    new_strength REAL,
                    old_layer TEXT,
                    new_layer TEXT,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS decay_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    memories_decayed INTEGER,
                    memories_forgotten INTEGER,
                    memories_promoted INTEGER,
                    storage_before_mb REAL,
                    storage_after_mb REAL
                );
                """
            )

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_memory(self, memory_data: Dict[str, Any]) -> str:
        memory_id = memory_data.get("id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, memory, user_id, agent_id, run_id, app_id,
                    metadata, categories, immutable, expiration_date,
                    created_at, updated_at, layer, strength, access_count,
                    last_accessed, embedding, related_memories, source_memories, tombstone
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    memory_data.get("memory", ""),
                    memory_data.get("user_id"),
                    memory_data.get("agent_id"),
                    memory_data.get("run_id"),
                    memory_data.get("app_id"),
                    json.dumps(memory_data.get("metadata", {})),
                    json.dumps(memory_data.get("categories", [])),
                    1 if memory_data.get("immutable", False) else 0,
                    memory_data.get("expiration_date"),
                    memory_data.get("created_at", now),
                    memory_data.get("updated_at", now),
                    memory_data.get("layer", "sml"),
                    memory_data.get("strength", 1.0),
                    memory_data.get("access_count", 0),
                    memory_data.get("last_accessed", now),
                    json.dumps(memory_data.get("embedding", [])),
                    json.dumps(memory_data.get("related_memories", [])),
                    json.dumps(memory_data.get("source_memories", [])),
                    1 if memory_data.get("tombstone", False) else 0,
                ),
            )

        self._log_event(memory_id, "ADD", new_value=memory_data.get("memory"))
        return memory_id

    def get_memory(self, memory_id: str, include_tombstoned: bool = False) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM memories WHERE id = ?"
        params = [memory_id]
        if not include_tombstoned:
            query += " AND tombstone = 0"

        with self._get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            if row:
                return self._row_to_dict(row)
        return None

    def get_all_memories(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        run_id: Optional[str] = None,
        app_id: Optional[str] = None,
        layer: Optional[str] = None,
        min_strength: float = 0.0,
        include_tombstoned: bool = False,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM memories WHERE strength >= ?"
        params: List[Any] = [min_strength]

        if not include_tombstoned:
            query += " AND tombstone = 0"
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if run_id:
            query += " AND run_id = ?"
            params.append(run_id)
        if app_id:
            query += " AND app_id = ?"
            params.append(app_id)
        if layer:
            query += " AND layer = ?"
            params.append(layer)

        query += " ORDER BY strength DESC"

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def update_memory(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        old_memory = self.get_memory(memory_id, include_tombstoned=True)
        if not old_memory:
            return False

        set_clauses = []
        params: List[Any] = []
        for key, value in updates.items():
            if key in {"metadata", "categories", "embedding", "related_memories", "source_memories"}:
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)

        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(memory_id)

        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE memories SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )

        self._log_event(
            memory_id,
            "UPDATE",
            old_value=old_memory.get("memory"),
            new_value=updates.get("memory"),
            old_strength=old_memory.get("strength"),
            new_strength=updates.get("strength"),
            old_layer=old_memory.get("layer"),
            new_layer=updates.get("layer"),
        )
        return True

    def delete_memory(self, memory_id: str, use_tombstone: bool = True) -> bool:
        if use_tombstone:
            return self.update_memory(memory_id, {"tombstone": 1})
        with self._get_connection() as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self._log_event(memory_id, "DELETE")
        return True

    def increment_access(self, memory_id: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE memories
                SET access_count = access_count + 1, last_accessed = ?
                WHERE id = ?
                """,
                (now, memory_id),
            )

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        for key in ["metadata", "categories", "embedding", "related_memories", "source_memories"]:
            if key in data and data[key]:
                data[key] = json.loads(data[key])
        data["immutable"] = bool(data.get("immutable", 0))
        data["tombstone"] = bool(data.get("tombstone", 0))
        return data

    def _log_event(self, memory_id: str, event: str, **kwargs: Any) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO memory_history (
                    memory_id, event, old_value, new_value,
                    old_strength, new_strength, old_layer, new_layer
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    event,
                    kwargs.get("old_value"),
                    kwargs.get("new_value"),
                    kwargs.get("old_strength"),
                    kwargs.get("new_strength"),
                    kwargs.get("old_layer"),
                    kwargs.get("new_layer"),
                ),
            )

    def log_event(self, memory_id: str, event: str, **kwargs: Any) -> None:
        """Public wrapper for logging custom events like DECAY or FUSE."""
        self._log_event(memory_id, event, **kwargs)

    def get_history(self, memory_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM memory_history WHERE memory_id = ? ORDER BY timestamp DESC",
                (memory_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def log_decay(self, decayed: int, forgotten: int, promoted: int, storage_before_mb: Optional[float] = None, storage_after_mb: Optional[float] = None) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO decay_log (memories_decayed, memories_forgotten, memories_promoted, storage_before_mb, storage_after_mb)
                VALUES (?, ?, ?, ?, ?)
                """,
                (decayed, forgotten, promoted, storage_before_mb, storage_after_mb),
            )

    def purge_tombstoned(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM memories WHERE tombstone = 1")
            return cursor.rowcount
