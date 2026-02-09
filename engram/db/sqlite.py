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

                -- CategoryMem tables
                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    category_type TEXT DEFAULT 'dynamic',
                    parent_id TEXT,
                    children_ids TEXT DEFAULT '[]',
                    memory_count INTEGER DEFAULT 0,
                    total_strength REAL DEFAULT 0.0,
                    access_count INTEGER DEFAULT 0,
                    last_accessed TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    embedding TEXT,
                    keywords TEXT DEFAULT '[]',
                    summary TEXT,
                    summary_updated_at TEXT,
                    related_ids TEXT DEFAULT '[]',
                    strength REAL DEFAULT 1.0,
                    FOREIGN KEY (parent_id) REFERENCES categories(id)
                );

                CREATE INDEX IF NOT EXISTS idx_category_type ON categories(category_type);
                CREATE INDEX IF NOT EXISTS idx_category_parent ON categories(parent_id);
                CREATE INDEX IF NOT EXISTS idx_category_strength ON categories(strength DESC);

                -- Episodic scenes
                CREATE TABLE IF NOT EXISTS scenes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    title TEXT,
                    summary TEXT,
                    topic TEXT,
                    location TEXT,
                    participants TEXT DEFAULT '[]',
                    memory_ids TEXT DEFAULT '[]',
                    start_time TEXT,
                    end_time TEXT,
                    embedding TEXT,
                    strength REAL DEFAULT 1.0,
                    access_count INTEGER DEFAULT 0,
                    tombstone INTEGER DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_scene_user ON scenes(user_id);
                CREATE INDEX IF NOT EXISTS idx_scene_start ON scenes(start_time DESC);

                -- Scene-Memory junction
                CREATE TABLE IF NOT EXISTS scene_memories (
                    scene_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    position INTEGER DEFAULT 0,
                    PRIMARY KEY (scene_id, memory_id),
                    FOREIGN KEY (scene_id) REFERENCES scenes(id),
                    FOREIGN KEY (memory_id) REFERENCES memories(id)
                );

                -- Character profiles
                CREATE TABLE IF NOT EXISTS profiles (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    name TEXT NOT NULL,
                    profile_type TEXT DEFAULT 'contact' CHECK (profile_type IN ('self', 'contact', 'entity')),
                    narrative TEXT,
                    facts TEXT DEFAULT '[]',
                    preferences TEXT DEFAULT '[]',
                    relationships TEXT DEFAULT '[]',
                    sentiment TEXT,
                    theory_of_mind TEXT DEFAULT '{}',
                    aliases TEXT DEFAULT '[]',
                    embedding TEXT,
                    strength REAL DEFAULT 1.0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_profile_user ON profiles(user_id);
                CREATE INDEX IF NOT EXISTS idx_profile_name ON profiles(name);
                CREATE INDEX IF NOT EXISTS idx_profile_type ON profiles(profile_type);

                -- Profile-Memory junction
                CREATE TABLE IF NOT EXISTS profile_memories (
                    profile_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    role TEXT DEFAULT 'mentioned' CHECK (role IN ('subject', 'mentioned', 'about')),
                    PRIMARY KEY (profile_id, memory_id),
                    FOREIGN KEY (profile_id) REFERENCES profiles(id),
                    FOREIGN KEY (memory_id) REFERENCES memories(id)
                );
                """
            )
            # Migration: add scene_id column to memories if missing
            self._migrate_add_column("memories", "scene_id", "TEXT")

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

    # CategoryMem methods
    def save_category(self, category_data: Dict[str, Any]) -> str:
        """Save or update a category."""
        category_id = category_data.get("id")
        if not category_id:
            return ""

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO categories (
                    id, name, description, category_type, parent_id,
                    children_ids, memory_count, total_strength, access_count,
                    last_accessed, created_at, embedding, keywords,
                    summary, summary_updated_at, related_ids, strength
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    category_id,
                    category_data.get("name", ""),
                    category_data.get("description", ""),
                    category_data.get("category_type", "dynamic"),
                    category_data.get("parent_id"),
                    json.dumps(category_data.get("children_ids", [])),
                    category_data.get("memory_count", 0),
                    category_data.get("total_strength", 0.0),
                    category_data.get("access_count", 0),
                    category_data.get("last_accessed"),
                    category_data.get("created_at"),
                    json.dumps(category_data.get("embedding")) if category_data.get("embedding") else None,
                    json.dumps(category_data.get("keywords", [])),
                    category_data.get("summary"),
                    category_data.get("summary_updated_at"),
                    json.dumps(category_data.get("related_ids", [])),
                    category_data.get("strength", 1.0),
                ),
            )
        return category_id

    def get_category(self, category_id: str) -> Optional[Dict[str, Any]]:
        """Get a category by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM categories WHERE id = ?",
                (category_id,)
            ).fetchone()
            if row:
                return self._category_row_to_dict(row)
        return None

    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Get all categories."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM categories ORDER BY strength DESC"
            ).fetchall()
            return [self._category_row_to_dict(row) for row in rows]

    def delete_category(self, category_id: str) -> bool:
        """Delete a category."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        return True

    def save_all_categories(self, categories: List[Dict[str, Any]]) -> int:
        """Save multiple categories (batch operation)."""
        count = 0
        for cat in categories:
            self.save_category(cat)
            count += 1
        return count

    def _category_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert a category row to dict."""
        data = dict(row)
        for key in ["children_ids", "keywords", "related_ids"]:
            if key in data and data[key]:
                data[key] = json.loads(data[key])
            else:
                data[key] = []
        if data.get("embedding"):
            data["embedding"] = json.loads(data["embedding"])
        return data

    def _migrate_add_column(self, table: str, column: str, col_type: str) -> None:
        """Add a column to an existing table if it doesn't already exist."""
        try:
            with self._get_connection() as conn:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass  # Column already exists

    # =========================================================================
    # Scene methods
    # =========================================================================

    def add_scene(self, scene_data: Dict[str, Any]) -> str:
        scene_id = scene_data.get("id", str(uuid.uuid4()))
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO scenes (
                    id, user_id, title, summary, topic, location,
                    participants, memory_ids, start_time, end_time,
                    embedding, strength, access_count, tombstone
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    scene_data.get("user_id"),
                    scene_data.get("title"),
                    scene_data.get("summary"),
                    scene_data.get("topic"),
                    scene_data.get("location"),
                    json.dumps(scene_data.get("participants", [])),
                    json.dumps(scene_data.get("memory_ids", [])),
                    scene_data.get("start_time"),
                    scene_data.get("end_time"),
                    json.dumps(scene_data.get("embedding")) if scene_data.get("embedding") else None,
                    scene_data.get("strength", 1.0),
                    scene_data.get("access_count", 0),
                    1 if scene_data.get("tombstone", False) else 0,
                ),
            )
        return scene_id

    def get_scene(self, scene_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM scenes WHERE id = ? AND tombstone = 0", (scene_id,)
            ).fetchone()
            if row:
                return self._scene_row_to_dict(row)
        return None

    def update_scene(self, scene_id: str, updates: Dict[str, Any]) -> bool:
        set_clauses = []
        params: List[Any] = []
        for key, value in updates.items():
            if key in {"participants", "memory_ids", "embedding"}:
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)
        if not set_clauses:
            return False
        params.append(scene_id)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE scenes SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
        return True

    def get_open_scene(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent scene without an end_time for a user."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM scenes
                WHERE user_id = ? AND end_time IS NULL AND tombstone = 0
                ORDER BY start_time DESC LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if row:
                return self._scene_row_to_dict(row)
        return None

    def get_scenes(
        self,
        user_id: Optional[str] = None,
        topic: Optional[str] = None,
        start_after: Optional[str] = None,
        start_before: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM scenes WHERE tombstone = 0"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if topic:
            query += " AND topic LIKE ?"
            params.append(f"%{topic}%")
        if start_after:
            query += " AND start_time >= ?"
            params.append(start_after)
        if start_before:
            query += " AND start_time <= ?"
            params.append(start_before)
        query += " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._scene_row_to_dict(row) for row in rows]

    def add_scene_memory(self, scene_id: str, memory_id: str, position: int = 0) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO scene_memories (scene_id, memory_id, position) VALUES (?, ?, ?)",
                (scene_id, memory_id, position),
            )

    def get_scene_memories(self, scene_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT m.* FROM memories m
                JOIN scene_memories sm ON m.id = sm.memory_id
                WHERE sm.scene_id = ? AND m.tombstone = 0
                ORDER BY sm.position
                """,
                (scene_id,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _scene_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        for key in ["participants", "memory_ids"]:
            if key in data and data[key]:
                data[key] = json.loads(data[key])
            else:
                data[key] = []
        if data.get("embedding"):
            data["embedding"] = json.loads(data["embedding"])
        data["tombstone"] = bool(data.get("tombstone", 0))
        return data

    # =========================================================================
    # Profile methods
    # =========================================================================

    def add_profile(self, profile_data: Dict[str, Any]) -> str:
        profile_id = profile_data.get("id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO profiles (
                    id, user_id, name, profile_type, narrative,
                    facts, preferences, relationships, sentiment,
                    theory_of_mind, aliases, embedding, strength,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    profile_data.get("user_id"),
                    profile_data.get("name", ""),
                    profile_data.get("profile_type", "contact"),
                    profile_data.get("narrative"),
                    json.dumps(profile_data.get("facts", [])),
                    json.dumps(profile_data.get("preferences", [])),
                    json.dumps(profile_data.get("relationships", [])),
                    profile_data.get("sentiment"),
                    json.dumps(profile_data.get("theory_of_mind", {})),
                    json.dumps(profile_data.get("aliases", [])),
                    json.dumps(profile_data.get("embedding")) if profile_data.get("embedding") else None,
                    profile_data.get("strength", 1.0),
                    profile_data.get("created_at", now),
                    profile_data.get("updated_at", now),
                ),
            )
        return profile_id

    def get_profile(self, profile_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM profiles WHERE id = ?", (profile_id,)
            ).fetchone()
            if row:
                return self._profile_row_to_dict(row)
        return None

    def update_profile(self, profile_id: str, updates: Dict[str, Any]) -> bool:
        set_clauses = []
        params: List[Any] = []
        for key, value in updates.items():
            if key in {"facts", "preferences", "relationships", "aliases", "theory_of_mind", "embedding"}:
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)
        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(profile_id)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE profiles SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
        return True

    def get_all_profiles(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM profiles"
        params: List[Any] = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY strength DESC"
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._profile_row_to_dict(row) for row in rows]

    def get_profile_by_name(self, name: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find a profile by exact name or alias match."""
        profiles = self.get_all_profiles(user_id=user_id)
        name_lower = name.lower()
        for p in profiles:
            if p["name"].lower() == name_lower:
                return p
            if name_lower in [a.lower() for a in p.get("aliases", [])]:
                return p
        return None

    def add_profile_memory(self, profile_id: str, memory_id: str, role: str = "mentioned") -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO profile_memories (profile_id, memory_id, role) VALUES (?, ?, ?)",
                (profile_id, memory_id, role),
            )

    def get_profile_memories(self, profile_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT m.*, pm.role AS profile_role FROM memories m
                JOIN profile_memories pm ON m.id = pm.memory_id
                WHERE pm.profile_id = ? AND m.tombstone = 0
                ORDER BY m.created_at DESC
                """,
                (profile_id,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def _profile_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        for key in ["facts", "preferences", "relationships", "aliases"]:
            if key in data and data[key]:
                data[key] = json.loads(data[key])
            else:
                data[key] = []
        if data.get("theory_of_mind"):
            data["theory_of_mind"] = json.loads(data["theory_of_mind"])
        else:
            data["theory_of_mind"] = {}
        if data.get("embedding"):
            data["embedding"] = json.loads(data["embedding"])
        return data

    def get_memories_by_category(
        self,
        category_id: str,
        limit: int = 100,
        min_strength: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Get memories belonging to a specific category."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM memories
                WHERE categories LIKE ? AND strength >= ? AND tombstone = 0
                ORDER BY strength DESC
                LIMIT ?
                """,
                (f'%"{category_id}"%', min_strength, limit),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]
