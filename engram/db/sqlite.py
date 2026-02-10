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
            # Legacy migration: add scene_id column to memories if missing.
            self._migrate_add_column_conn(conn, "memories", "scene_id", "TEXT")
            # v2 schema + idempotent migrations.
            self._ensure_v2_schema(conn)

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _ensure_v2_schema(self, conn: sqlite3.Connection) -> None:
        """Create and migrate Engram v2 schema in-place (idempotent)."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        migrations: Dict[str, str] = {
            "v2_001": """
                CREATE TABLE IF NOT EXISTS views (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    agent_id TEXT,
                    timestamp TEXT NOT NULL,
                    place_type TEXT,
                    place_value TEXT,
                    topic_label TEXT,
                    topic_embedding_ref TEXT,
                    characters TEXT DEFAULT '[]',
                    raw_text TEXT,
                    signals TEXT DEFAULT '{}',
                    scene_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_views_user_time ON views(user_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_views_scene ON views(scene_id);
            """,
            "v2_002": """
                CREATE TABLE IF NOT EXISTS proposal_commits (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    agent_id TEXT,
                    scope TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    checks TEXT DEFAULT '{}',
                    preview TEXT DEFAULT '{}',
                    provenance TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_proposal_commits_user ON proposal_commits(user_id);
                CREATE INDEX IF NOT EXISTS idx_proposal_commits_status ON proposal_commits(status);

                CREATE TABLE IF NOT EXISTS proposal_changes (
                    id TEXT PRIMARY KEY,
                    commit_id TEXT NOT NULL,
                    op TEXT NOT NULL,
                    target TEXT NOT NULL,
                    target_id TEXT,
                    patch TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (commit_id) REFERENCES proposal_commits(id)
                );
                CREATE INDEX IF NOT EXISTS idx_proposal_changes_commit ON proposal_changes(commit_id);
            """,
            "v2_003": """
                CREATE TABLE IF NOT EXISTS conflict_stash (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    conflict_key TEXT NOT NULL,
                    existing TEXT DEFAULT '{}',
                    proposed TEXT DEFAULT '{}',
                    resolution TEXT NOT NULL DEFAULT 'UNRESOLVED',
                    source_commit_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    resolved_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_conflict_stash_user ON conflict_stash(user_id);
                CREATE INDEX IF NOT EXISTS idx_conflict_stash_resolution ON conflict_stash(resolution);
            """,
            "v2_004": """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    agent_id TEXT,
                    allowed_confidentiality_scopes TEXT DEFAULT '[]',
                    capabilities TEXT DEFAULT '[]',
                    expires_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);
            """,
            "v2_005": """
                CREATE TABLE IF NOT EXISTS memory_refcounts (
                    memory_id TEXT PRIMARY KEY,
                    strong_count INTEGER DEFAULT 0,
                    weak_count INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (memory_id) REFERENCES memories(id)
                );

                CREATE TABLE IF NOT EXISTS memory_subscribers (
                    id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    subscriber TEXT NOT NULL,
                    ref_type TEXT NOT NULL CHECK(ref_type IN ('strong','weak')),
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(memory_id, subscriber, ref_type),
                    FOREIGN KEY (memory_id) REFERENCES memories(id)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_subscribers_memory ON memory_subscribers(memory_id);
            """,
            "v2_006": """
                CREATE TABLE IF NOT EXISTS daily_digests (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    digest_date TEXT NOT NULL,
                    payload TEXT DEFAULT '{}',
                    generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, digest_date)
                );
                CREATE INDEX IF NOT EXISTS idx_daily_digests_user_date ON daily_digests(user_id, digest_date);
            """,
            "v2_007": """
                CREATE TABLE IF NOT EXISTS invariants (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    invariant_key TEXT NOT NULL,
                    invariant_value TEXT NOT NULL,
                    category TEXT DEFAULT 'identity',
                    confidence REAL DEFAULT 0.0,
                    source_memory_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, invariant_key)
                );
                CREATE INDEX IF NOT EXISTS idx_invariants_user ON invariants(user_id);
            """,
            "v2_008": """
                CREATE TABLE IF NOT EXISTS agent_trust (
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    total_proposals INTEGER DEFAULT 0,
                    approved_proposals INTEGER DEFAULT 0,
                    rejected_proposals INTEGER DEFAULT 0,
                    auto_stashed_proposals INTEGER DEFAULT 0,
                    last_proposed_at TEXT,
                    last_approved_at TEXT,
                    trust_score REAL DEFAULT 0.0,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, agent_id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_trust_user ON agent_trust(user_id);
                CREATE INDEX IF NOT EXISTS idx_agent_trust_score ON agent_trust(trust_score DESC);
            """,
            "v2_009": """
                CREATE TABLE IF NOT EXISTS namespaces (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, name)
                );
                CREATE INDEX IF NOT EXISTS idx_namespaces_user ON namespaces(user_id);

                CREATE TABLE IF NOT EXISTS namespace_permissions (
                    id TEXT PRIMARY KEY,
                    namespace_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    granted_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT,
                    FOREIGN KEY (namespace_id) REFERENCES namespaces(id),
                    UNIQUE(namespace_id, user_id, agent_id, capability)
                );
                CREATE INDEX IF NOT EXISTS idx_ns_permissions_agent ON namespace_permissions(user_id, agent_id);
                CREATE INDEX IF NOT EXISTS idx_ns_permissions_namespace ON namespace_permissions(namespace_id);
            """,
            "v2_011": """
                CREATE TABLE IF NOT EXISTS handoff_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    repo TEXT,
                    status TEXT NOT NULL DEFAULT 'paused'
                        CHECK (status IN ('active', 'paused', 'completed', 'abandoned')),
                    task_summary TEXT NOT NULL,
                    decisions_made TEXT DEFAULT '[]',
                    files_touched TEXT DEFAULT '[]',
                    todos_remaining TEXT DEFAULT '[]',
                    context_snapshot TEXT,
                    linked_memory_ids TEXT DEFAULT '[]',
                    linked_scene_ids TEXT DEFAULT '[]',
                    started_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    ended_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_handoff_user ON handoff_sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_handoff_agent ON handoff_sessions(agent_id);
                CREATE INDEX IF NOT EXISTS idx_handoff_repo ON handoff_sessions(repo);
                CREATE INDEX IF NOT EXISTS idx_handoff_status ON handoff_sessions(status);
                CREATE INDEX IF NOT EXISTS idx_handoff_updated ON handoff_sessions(updated_at DESC);

                CREATE TABLE IF NOT EXISTS handoff_session_memories (
                    session_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    relevance_score REAL DEFAULT 1.0,
                    PRIMARY KEY (session_id, memory_id),
                    FOREIGN KEY (session_id) REFERENCES handoff_sessions(id),
                    FOREIGN KEY (memory_id) REFERENCES memories(id)
                );
                CREATE INDEX IF NOT EXISTS idx_hsm_session ON handoff_session_memories(session_id);
            """,
            "v2_010": """
                CREATE TABLE IF NOT EXISTS agent_policies (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    allowed_confidentiality_scopes TEXT DEFAULT '[]',
                    allowed_capabilities TEXT DEFAULT '[]',
                    allowed_namespaces TEXT DEFAULT '[]',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, agent_id)
                );
                CREATE INDEX IF NOT EXISTS idx_agent_policies_user ON agent_policies(user_id);
                CREATE INDEX IF NOT EXISTS idx_agent_policies_agent ON agent_policies(agent_id);
            """,
            "v2_012": """
                CREATE TABLE IF NOT EXISTS handoff_lanes (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    repo_id TEXT,
                    repo_path TEXT,
                    branch TEXT,
                    lane_type TEXT DEFAULT 'general',
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'paused', 'completed', 'abandoned')),
                    objective TEXT,
                    current_state TEXT DEFAULT '{}',
                    namespace TEXT DEFAULT 'default',
                    confidentiality_scope TEXT DEFAULT 'work',
                    last_checkpoint_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    version INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_handoff_lanes_user ON handoff_lanes(user_id);
                CREATE INDEX IF NOT EXISTS idx_handoff_lanes_repo ON handoff_lanes(repo_id);
                CREATE INDEX IF NOT EXISTS idx_handoff_lanes_status ON handoff_lanes(status);
                CREATE INDEX IF NOT EXISTS idx_handoff_lanes_recent ON handoff_lanes(last_checkpoint_at DESC, created_at DESC);

                CREATE TABLE IF NOT EXISTS handoff_checkpoints (
                    id TEXT PRIMARY KEY,
                    lane_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    agent_role TEXT,
                    event_type TEXT DEFAULT 'tool_complete',
                    task_summary TEXT,
                    decisions_made TEXT DEFAULT '[]',
                    files_touched TEXT DEFAULT '[]',
                    todos_remaining TEXT DEFAULT '[]',
                    blockers TEXT DEFAULT '[]',
                    key_commands TEXT DEFAULT '[]',
                    test_results TEXT DEFAULT '[]',
                    merge_conflicts TEXT DEFAULT '[]',
                    context_snapshot TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (lane_id) REFERENCES handoff_lanes(id)
                );
                CREATE INDEX IF NOT EXISTS idx_handoff_cp_lane ON handoff_checkpoints(lane_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_handoff_cp_user ON handoff_checkpoints(user_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS handoff_checkpoint_memories (
                    checkpoint_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    relevance_score REAL DEFAULT 1.0,
                    PRIMARY KEY (checkpoint_id, memory_id),
                    FOREIGN KEY (checkpoint_id) REFERENCES handoff_checkpoints(id),
                    FOREIGN KEY (memory_id) REFERENCES memories(id)
                );
                CREATE INDEX IF NOT EXISTS idx_hcm_checkpoint ON handoff_checkpoint_memories(checkpoint_id);

                CREATE TABLE IF NOT EXISTS handoff_checkpoint_scenes (
                    checkpoint_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    relevance_score REAL DEFAULT 1.0,
                    PRIMARY KEY (checkpoint_id, scene_id),
                    FOREIGN KEY (checkpoint_id) REFERENCES handoff_checkpoints(id),
                    FOREIGN KEY (scene_id) REFERENCES scenes(id)
                );
                CREATE INDEX IF NOT EXISTS idx_hcs_checkpoint ON handoff_checkpoint_scenes(checkpoint_id);

                CREATE TABLE IF NOT EXISTS handoff_lane_conflicts (
                    id TEXT PRIMARY KEY,
                    lane_id TEXT NOT NULL,
                    checkpoint_id TEXT,
                    user_id TEXT NOT NULL,
                    conflict_fields TEXT DEFAULT '[]',
                    previous_state TEXT DEFAULT '{}',
                    incoming_state TEXT DEFAULT '{}',
                    resolved_state TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (lane_id) REFERENCES handoff_lanes(id),
                    FOREIGN KEY (checkpoint_id) REFERENCES handoff_checkpoints(id)
                );
                CREATE INDEX IF NOT EXISTS idx_handoff_conflicts_lane ON handoff_lane_conflicts(lane_id, created_at DESC);
            """,
        }

        for version, ddl in migrations.items():
            if not self._is_migration_applied(conn, version):
                conn.executescript(ddl)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations (version) VALUES (?)",
                    (version,),
                )

        # v2 columns on existing canonical tables.
        self._migrate_add_column_conn(conn, "memories", "confidentiality_scope", "TEXT DEFAULT 'work'")
        self._migrate_add_column_conn(conn, "memories", "source_type", "TEXT")
        self._migrate_add_column_conn(conn, "memories", "source_app", "TEXT")
        self._migrate_add_column_conn(conn, "memories", "source_event_id", "TEXT")
        self._migrate_add_column_conn(conn, "memories", "decay_lambda", "REAL DEFAULT 0.12")
        self._migrate_add_column_conn(conn, "memories", "status", "TEXT DEFAULT 'active'")
        self._migrate_add_column_conn(conn, "memories", "importance", "REAL DEFAULT 0.5")
        self._migrate_add_column_conn(conn, "memories", "sensitivity", "TEXT DEFAULT 'normal'")
        self._migrate_add_column_conn(conn, "memories", "namespace", "TEXT DEFAULT 'default'")

        self._migrate_add_column_conn(conn, "scenes", "layer", "TEXT DEFAULT 'sml'")
        self._migrate_add_column_conn(conn, "scenes", "scene_strength", "REAL DEFAULT 1.0")
        self._migrate_add_column_conn(conn, "scenes", "topic_embedding_ref", "TEXT")
        self._migrate_add_column_conn(conn, "scenes", "namespace", "TEXT DEFAULT 'default'")

        self._migrate_add_column_conn(conn, "profiles", "role_bias", "TEXT")
        self._migrate_add_column_conn(conn, "profiles", "profile_summary", "TEXT")
        self._migrate_add_column_conn(conn, "sessions", "namespaces", "TEXT DEFAULT '[]'")
        self._migrate_add_column_conn(conn, "memory_subscribers", "last_seen_at", "TEXT")
        self._migrate_add_column_conn(conn, "memory_subscribers", "expires_at", "TEXT")
        self._migrate_add_column_conn(conn, "handoff_sessions", "repo_id", "TEXT")
        self._migrate_add_column_conn(conn, "handoff_sessions", "blockers", "TEXT DEFAULT '[]'")
        self._migrate_add_column_conn(conn, "handoff_sessions", "key_commands", "TEXT DEFAULT '[]'")
        self._migrate_add_column_conn(conn, "handoff_sessions", "test_results", "TEXT DEFAULT '[]'")
        self._migrate_add_column_conn(conn, "handoff_sessions", "lane_id", "TEXT")
        self._migrate_add_column_conn(conn, "handoff_sessions", "last_checkpoint_at", "TEXT")
        self._migrate_add_column_conn(conn, "handoff_sessions", "namespace", "TEXT DEFAULT 'default'")
        self._migrate_add_column_conn(conn, "handoff_sessions", "confidentiality_scope", "TEXT DEFAULT 'work'")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_subscribers_expires ON memory_subscribers(expires_at)")

        # Backfills.
        conn.execute(
            """
            UPDATE memories
            SET confidentiality_scope = 'work'
            WHERE confidentiality_scope IS NULL OR confidentiality_scope = ''
            """
        )
        conn.execute(
            """
            UPDATE memories
            SET status = 'active'
            WHERE status IS NULL OR status = ''
            """
        )
        conn.execute(
            """
            UPDATE memories
            SET namespace = 'default'
            WHERE namespace IS NULL OR namespace = ''
            """
        )
        conn.execute(
            """
            UPDATE scenes
            SET namespace = 'default'
            WHERE namespace IS NULL OR namespace = ''
            """
        )
        conn.execute(
            """
            UPDATE sessions
            SET namespaces = '[]'
            WHERE namespaces IS NULL OR namespaces = ''
            """
        )
        conn.execute(
            """
            UPDATE handoff_sessions
            SET blockers = COALESCE(NULLIF(blockers, ''), '[]'),
                key_commands = COALESCE(NULLIF(key_commands, ''), '[]'),
                test_results = COALESCE(NULLIF(test_results, ''), '[]'),
                namespace = COALESCE(NULLIF(namespace, ''), 'default'),
                confidentiality_scope = COALESCE(NULLIF(confidentiality_scope, ''), 'work'),
                repo_id = COALESCE(NULLIF(repo_id, ''), repo),
                last_checkpoint_at = COALESCE(last_checkpoint_at, updated_at, created_at)
            """
        )
        conn.execute(
            """
            UPDATE memories
            SET decay_lambda = 0.12
            WHERE decay_lambda IS NULL
            """
        )
        conn.execute(
            """
            UPDATE memory_subscribers
            SET
                last_seen_at = COALESCE(last_seen_at, created_at),
                expires_at = COALESCE(
                    expires_at,
                    CASE
                        WHEN ref_type = 'weak' THEN datetime(created_at, '+14 days')
                        ELSE NULL
                    END
                )
            """
        )
        conn.execute(
            """
            UPDATE memories
            SET importance = COALESCE(
                CASE
                    WHEN json_extract(metadata, '$.importance') IS NOT NULL
                    THEN json_extract(metadata, '$.importance')
                    ELSE importance
                END,
                0.5
            )
            """
        )
        conn.execute(
            """
            UPDATE memories
            SET sensitivity = CASE
                WHEN lower(memory) LIKE '%password%' OR lower(memory) LIKE '%api key%' OR lower(memory) LIKE '%token%'
                    THEN 'secret'
                WHEN lower(memory) LIKE '%health%' OR lower(memory) LIKE '%medical%'
                    THEN 'sensitive'
                WHEN lower(memory) LIKE '%bank%' OR lower(memory) LIKE '%salary%' OR lower(memory) LIKE '%credit card%'
                    THEN 'sensitive'
                ELSE COALESCE(NULLIF(sensitivity, ''), 'normal')
            END
            """
        )
        # Keep memory_refcounts bootstrapped for existing memories.
        conn.execute(
            """
            INSERT OR IGNORE INTO memory_refcounts (memory_id, strong_count, weak_count)
            SELECT id, 0, 0 FROM memories
            """
        )
        self._seed_default_namespaces(conn)
        self._seed_invariants(conn)

    def _seed_default_namespaces(self, conn: sqlite3.Connection) -> None:
        users = conn.execute(
            """
            SELECT DISTINCT user_id FROM memories
            WHERE user_id IS NOT NULL AND user_id != ''
            """
        ).fetchall()
        now = datetime.utcnow().isoformat()
        for row in users:
            user_id = row["user_id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO namespaces (id, user_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), user_id, "default", "Default namespace", now, now),
            )

    def _seed_invariants(self, conn: sqlite3.Connection) -> None:
        """Bootstrap protected invariants from self profile and explicit memories."""
        rows = conn.execute(
            """
            SELECT id, user_id, memory, metadata
            FROM memories
            WHERE tombstone = 0 AND (
                lower(memory) LIKE 'name:%'
                OR lower(memory) LIKE 'my name is %'
                OR lower(memory) LIKE '%@%'
                OR json_extract(metadata, '$.policy_explicit') = 1
                OR json_extract(metadata, '$.policy_explicit') = 'true'
            )
            ORDER BY created_at DESC
            """
        ).fetchall()

        for row in rows:
            memory = (row["memory"] or "").strip()
            memory_lower = memory.lower()
            key = None
            value = None
            category = "identity"

            if memory_lower.startswith("name:"):
                key = "identity.name"
                value = memory.split(":", 1)[1].strip()
            elif memory_lower.startswith("my name is "):
                key = "identity.name"
                value = memory[11:].strip()
            elif "@" in memory and " " not in memory.strip():
                key = "identity.primary_email"
                value = memory.strip()
            elif "email" in memory_lower and "@" in memory:
                key = "identity.primary_email"
                value = memory.strip()

            if not key or not value:
                continue

            conn.execute(
                """
                INSERT INTO invariants (
                    id, user_id, invariant_key, invariant_value, category, confidence, source_memory_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, invariant_key) DO UPDATE SET
                    invariant_value=excluded.invariant_value,
                    confidence=max(invariants.confidence, excluded.confidence),
                    source_memory_id=excluded.source_memory_id,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    str(uuid.uuid4()),
                    row["user_id"] or "default",
                    key,
                    value,
                    category,
                    0.9,
                    row["id"],
                ),
            )

        # Seed from self profile summary/name if available.
        profile_rows = conn.execute(
            """
            SELECT id, user_id, name
            FROM profiles
            WHERE profile_type = 'self'
            """
        ).fetchall()
        for row in profile_rows:
            if not row["name"] or row["name"].lower() == "self":
                continue
            conn.execute(
                """
                INSERT INTO invariants (
                    id, user_id, invariant_key, invariant_value, category, confidence, source_memory_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, invariant_key) DO NOTHING
                """,
                (
                    str(uuid.uuid4()),
                    row["user_id"] or "default",
                    "identity.name",
                    row["name"],
                    "identity",
                    0.95,
                    None,
                ),
            )

    def _is_migration_applied(self, conn: sqlite3.Connection, version: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version = ?",
            (version,),
        ).fetchone()
        return row is not None

    def _migrate_add_column_conn(
        self,
        conn: sqlite3.Connection,
        table: str,
        column: str,
        col_type: str,
    ) -> None:
        """Add a column using an existing connection, if missing."""
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        except sqlite3.OperationalError:
            pass

    def add_memory(self, memory_data: Dict[str, Any]) -> str:
        memory_id = memory_data.get("id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()
        metadata = memory_data.get("metadata", {}) or {}
        source_app = memory_data.get("source_app") or memory_data.get("app_id") or metadata.get("source_app")

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, memory, user_id, agent_id, run_id, app_id,
                    metadata, categories, immutable, expiration_date,
                    created_at, updated_at, layer, strength, access_count,
                    last_accessed, embedding, related_memories, source_memories, tombstone,
                    confidentiality_scope, namespace, source_type, source_app, source_event_id, decay_lambda,
                    status, importance, sensitivity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    memory_data.get("confidentiality_scope", "work"),
                    memory_data.get("namespace", metadata.get("namespace", "default")),
                    memory_data.get("source_type") or metadata.get("source_type") or "mcp",
                    source_app,
                    memory_data.get("source_event_id") or metadata.get("source_event_id"),
                    memory_data.get("decay_lambda", 0.12),
                    memory_data.get("status", "active"),
                    memory_data.get("importance", metadata.get("importance", 0.5)),
                    memory_data.get("sensitivity", metadata.get("sensitivity", "normal")),
                ),
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO memory_refcounts (memory_id, strong_count, weak_count)
                VALUES (?, 0, 0)
                """,
                (memory_id,),
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
        namespace: Optional[str] = None,
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
        if namespace:
            query += " AND namespace = ?"
            params.append(namespace)

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
        with self._get_connection() as conn:
            self._migrate_add_column_conn(conn, table, column, col_type)

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
                    embedding, strength, access_count, tombstone,
                    layer, scene_strength, topic_embedding_ref, namespace
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    scene_data.get("layer", "sml"),
                    scene_data.get("scene_strength", scene_data.get("strength", 1.0)),
                    scene_data.get("topic_embedding_ref"),
                    scene_data.get("namespace", "default"),
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
        namespace: Optional[str] = None,
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
        if namespace:
            query += " AND namespace = ?"
            params.append(namespace)
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
                    created_at, updated_at, role_bias, profile_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    profile_data.get("role_bias"),
                    profile_data.get("profile_summary"),
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

    # =========================================================================
    # v2 Session methods
    # =========================================================================

    def create_session(self, session_data: Dict[str, Any]) -> str:
        session_id = session_data.get("id", str(uuid.uuid4()))
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                    id, token_hash, user_id, agent_id,
                    allowed_confidentiality_scopes, capabilities, namespaces, expires_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    session_data.get("token_hash"),
                    session_data.get("user_id"),
                    session_data.get("agent_id"),
                    json.dumps(session_data.get("allowed_confidentiality_scopes", [])),
                    json.dumps(session_data.get("capabilities", [])),
                    json.dumps(session_data.get("namespaces", [])),
                    session_data.get("expires_at"),
                    session_data.get("revoked_at"),
                ),
            )
        return session_id

    def get_session_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row:
                data = dict(row)
                data["allowed_confidentiality_scopes"] = self._parse_json_value(
                    data.get("allowed_confidentiality_scopes"), []
                )
                data["capabilities"] = self._parse_json_value(data.get("capabilities"), [])
                data["namespaces"] = self._parse_json_value(data.get("namespaces"), [])
                return data
        return None

    def revoke_session(self, session_id: str) -> bool:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), session_id),
            )
        return True

    # =========================================================================
    # v2 Staging / proposal methods
    # =========================================================================

    def add_proposal_commit(self, commit_data: Dict[str, Any], changes: Optional[List[Dict[str, Any]]] = None) -> str:
        commit_id = commit_data.get("id", str(uuid.uuid4()))
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO proposal_commits (
                    id, user_id, agent_id, scope, status, checks, preview, provenance, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_id,
                    commit_data.get("user_id"),
                    commit_data.get("agent_id"),
                    commit_data.get("scope"),
                    commit_data.get("status", "PENDING"),
                    json.dumps(commit_data.get("checks", {})),
                    json.dumps(commit_data.get("preview", {})),
                    json.dumps(commit_data.get("provenance", {})),
                    commit_data.get("created_at", datetime.utcnow().isoformat()),
                    commit_data.get("updated_at", datetime.utcnow().isoformat()),
                ),
            )
            for change in changes or []:
                conn.execute(
                    """
                    INSERT INTO proposal_changes (
                        id, commit_id, op, target, target_id, patch, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        change.get("id", str(uuid.uuid4())),
                        commit_id,
                        change.get("op", "ADD"),
                        change.get("target", "memory_item"),
                        change.get("target_id"),
                        json.dumps(change.get("patch", {})),
                        change.get("created_at", datetime.utcnow().isoformat()),
                    ),
                )
        return commit_id

    def get_proposal_commit(self, commit_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM proposal_commits WHERE id = ?",
                (commit_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["checks"] = self._parse_json_value(data.get("checks"), {})
            data["preview"] = self._parse_json_value(data.get("preview"), {})
            data["provenance"] = self._parse_json_value(data.get("provenance"), {})
            data["changes"] = self.get_proposal_changes(commit_id)
            return data

    def list_proposal_commits(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM proposal_commits WHERE 1=1"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        commits: List[Dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["checks"] = self._parse_json_value(data.get("checks"), {})
            data["preview"] = self._parse_json_value(data.get("preview"), {})
            data["provenance"] = self._parse_json_value(data.get("provenance"), {})
            commits.append(data)
        return commits

    def get_proposal_changes(self, commit_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM proposal_changes WHERE commit_id = ? ORDER BY created_at ASC",
                (commit_id,),
            ).fetchall()
        changes = [dict(row) for row in rows]
        for change in changes:
            change["patch"] = self._parse_json_value(change.get("patch"), {})
        return changes

    def update_proposal_commit(self, commit_id: str, updates: Dict[str, Any]) -> bool:
        set_clauses = []
        params: List[Any] = []
        for key, value in updates.items():
            if key in {"checks", "preview", "provenance"}:
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)
        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(commit_id)
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE proposal_commits SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
        return True

    def transition_proposal_commit_status(
        self,
        commit_id: str,
        *,
        from_statuses: Iterable[str],
        to_status: str,
        updates: Optional[Dict[str, Any]] = None,
    ) -> bool:
        normalized_from = [str(status or "").upper() for status in from_statuses if str(status or "").strip()]
        if not normalized_from:
            return False

        set_clauses = ["status = ?", "updated_at = ?"]
        params: List[Any] = [str(to_status or "").upper(), datetime.utcnow().isoformat()]
        for key, value in (updates or {}).items():
            if key in {"checks", "preview", "provenance"}:
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)

        placeholders = ", ".join("?" for _ in normalized_from)
        params.append(commit_id)
        params.extend(normalized_from)

        with self._get_connection() as conn:
            cursor = conn.execute(
                f"""
                UPDATE proposal_commits
                SET {', '.join(set_clauses)}
                WHERE id = ? AND status IN ({placeholders})
                """,
                params,
            )
            return cursor.rowcount > 0

    # =========================================================================
    # v2 Conflict stash methods
    # =========================================================================

    def add_conflict_stash(self, stash_data: Dict[str, Any]) -> str:
        stash_id = stash_data.get("id", str(uuid.uuid4()))
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO conflict_stash (
                    id, user_id, conflict_key, existing, proposed, resolution, source_commit_id, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stash_id,
                    stash_data.get("user_id"),
                    stash_data.get("conflict_key"),
                    json.dumps(stash_data.get("existing", {})),
                    json.dumps(stash_data.get("proposed", {})),
                    stash_data.get("resolution", "UNRESOLVED"),
                    stash_data.get("source_commit_id"),
                    stash_data.get("created_at", datetime.utcnow().isoformat()),
                    stash_data.get("resolved_at"),
                ),
            )
        return stash_id

    def get_conflict_stash(self, stash_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM conflict_stash WHERE id = ?",
                (stash_id,),
            ).fetchone()
            if not row:
                return None
            data = dict(row)
            data["existing"] = self._parse_json_value(data.get("existing"), {})
            data["proposed"] = self._parse_json_value(data.get("proposed"), {})
            return data

    def list_conflict_stash(
        self,
        user_id: Optional[str] = None,
        resolution: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM conflict_stash WHERE 1=1"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if resolution:
            query += " AND resolution = ?"
            params.append(resolution)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        results: List[Dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["existing"] = self._parse_json_value(data.get("existing"), {})
            data["proposed"] = self._parse_json_value(data.get("proposed"), {})
            results.append(data)
        return results

    def resolve_conflict_stash(self, stash_id: str, resolution: str) -> bool:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE conflict_stash
                SET resolution = ?, resolved_at = ?
                WHERE id = ?
                """,
                (resolution, datetime.utcnow().isoformat(), stash_id),
            )
        return True

    # =========================================================================
    # v2 View methods
    # =========================================================================

    def add_view(self, view_data: Dict[str, Any]) -> str:
        view_id = view_data.get("id", str(uuid.uuid4()))
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO views (
                    id, user_id, agent_id, timestamp, place_type, place_value,
                    topic_label, topic_embedding_ref, characters, raw_text,
                    signals, scene_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    view_id,
                    view_data.get("user_id"),
                    view_data.get("agent_id"),
                    view_data.get("timestamp", datetime.utcnow().isoformat()),
                    view_data.get("place_type"),
                    view_data.get("place_value"),
                    view_data.get("topic_label"),
                    view_data.get("topic_embedding_ref"),
                    json.dumps(view_data.get("characters", [])),
                    view_data.get("raw_text"),
                    json.dumps(view_data.get("signals", {})),
                    view_data.get("scene_id"),
                    view_data.get("created_at", datetime.utcnow().isoformat()),
                ),
            )
        return view_id

    def get_views(
        self,
        user_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM views WHERE 1=1"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if scene_id:
            query += " AND scene_id = ?"
            params.append(scene_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        views = [dict(row) for row in rows]
        for view in views:
            view["characters"] = self._parse_json_value(view.get("characters"), [])
            view["signals"] = self._parse_json_value(view.get("signals"), {})
        return views

    # =========================================================================
    # v2 Refcount methods
    # =========================================================================

    def get_memory_refcount(self, memory_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM memory_refcounts WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
        if not row:
            return {"memory_id": memory_id, "strong": 0, "weak": 0, "subscribers": []}
        subscribers = self.list_memory_subscribers(memory_id)
        return {
            "memory_id": memory_id,
            "strong": int(row["strong_count"]),
            "weak": int(row["weak_count"]),
            "subscribers": subscribers,
        }

    def adjust_memory_refcount(self, memory_id: str, strong_delta: int = 0, weak_delta: int = 0) -> Dict[str, Any]:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO memory_refcounts (memory_id, strong_count, weak_count)
                VALUES (?, 0, 0)
                """,
                (memory_id,),
            )
            conn.execute(
                """
                UPDATE memory_refcounts
                SET
                    strong_count = CASE WHEN strong_count + ? < 0 THEN 0 ELSE strong_count + ? END,
                    weak_count = CASE WHEN weak_count + ? < 0 THEN 0 ELSE weak_count + ? END,
                    updated_at = ?
                WHERE memory_id = ?
                """,
                (
                    strong_delta,
                    strong_delta,
                    weak_delta,
                    weak_delta,
                    datetime.utcnow().isoformat(),
                    memory_id,
                ),
            )
        return self.get_memory_refcount(memory_id)

    def add_memory_subscriber(
        self,
        memory_id: str,
        subscriber: str,
        ref_type: str = "weak",
        ttl_hours: Optional[int] = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        expires_at = None
        if ttl_hours is not None:
            try:
                ttl_value = int(ttl_hours)
            except Exception:
                ttl_value = 0
            if ttl_value > 0:
                expires_at = datetime.utcfromtimestamp(
                    datetime.utcnow().timestamp() + ttl_value * 3600
                ).isoformat()
            elif ttl_value < 0:
                expires_at = datetime.utcfromtimestamp(
                    datetime.utcnow().timestamp() + ttl_value * 3600
                ).isoformat()
        elif ref_type == "weak":
            expires_at = datetime.utcfromtimestamp(
                datetime.utcnow().timestamp() + 14 * 24 * 3600
            ).isoformat()

        with self._get_connection() as conn:
            existing = conn.execute(
                """
                SELECT 1 FROM memory_subscribers
                WHERE memory_id = ? AND subscriber = ? AND ref_type = ?
                """,
                (memory_id, subscriber, ref_type),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO memory_subscribers (id, memory_id, subscriber, ref_type, created_at, last_seen_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id, subscriber, ref_type) DO UPDATE SET
                    last_seen_at=excluded.last_seen_at,
                    expires_at=excluded.expires_at
                """,
                (
                    str(uuid.uuid4()),
                    memory_id,
                    subscriber,
                    ref_type,
                    now,
                    now,
                    expires_at,
                ),
            )
        if existing is None:
            self.adjust_memory_refcount(
                memory_id,
                strong_delta=1 if ref_type == "strong" else 0,
                weak_delta=1 if ref_type == "weak" else 0,
            )

    def remove_memory_subscriber(self, memory_id: str, subscriber: str, ref_type: str = "weak") -> None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM memory_subscribers
                WHERE memory_id = ? AND subscriber = ? AND ref_type = ?
                """,
                (memory_id, subscriber, ref_type),
            )
        if cursor.rowcount > 0:
            self.adjust_memory_refcount(
                memory_id,
                strong_delta=-1 if ref_type == "strong" else 0,
                weak_delta=-1 if ref_type == "weak" else 0,
            )

    def list_memory_subscribers(self, memory_id: str) -> List[str]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT subscriber, ref_type
                FROM memory_subscribers
                WHERE memory_id = ?
                ORDER BY created_at ASC
                """,
                (memory_id,),
            ).fetchall()
        return [f"{row['subscriber']}:{row['ref_type']}" for row in rows]

    def cleanup_stale_memory_subscribers(self, now_iso: Optional[str] = None) -> int:
        now_iso = now_iso or datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT memory_id, subscriber, ref_type
                FROM memory_subscribers
                WHERE expires_at IS NOT NULL AND expires_at <= ?
                """,
                (now_iso,),
            ).fetchall()
            if not rows:
                return 0
            removed = 0
            for row in rows:
                cursor = conn.execute(
                    """
                    DELETE FROM memory_subscribers
                    WHERE memory_id = ? AND subscriber = ? AND ref_type = ?
                    """,
                    (row["memory_id"], row["subscriber"], row["ref_type"]),
                )
                if cursor.rowcount <= 0:
                    continue
                removed += cursor.rowcount
                conn.execute(
                    """
                    UPDATE memory_refcounts
                    SET
                        strong_count = CASE
                            WHEN ? = 'strong' THEN CASE WHEN strong_count - 1 < 0 THEN 0 ELSE strong_count - 1 END
                            ELSE strong_count
                        END,
                        weak_count = CASE
                            WHEN ? = 'weak' THEN CASE WHEN weak_count - 1 < 0 THEN 0 ELSE weak_count - 1 END
                            ELSE weak_count
                        END,
                        updated_at = ?
                    WHERE memory_id = ?
                    """,
                    (row["ref_type"], row["ref_type"], now_iso, row["memory_id"]),
                )
        return removed

    # =========================================================================
    # v2 Daily digest methods
    # =========================================================================

    def upsert_daily_digest(self, user_id: str, digest_date: str, payload: Dict[str, Any]) -> str:
        digest_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO daily_digests (id, user_id, digest_date, payload, generated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, digest_date) DO UPDATE SET
                    payload=excluded.payload,
                    generated_at=excluded.generated_at
                """,
                (
                    digest_id,
                    user_id,
                    digest_date,
                    json.dumps(payload),
                    datetime.utcnow().isoformat(),
                ),
            )
        return digest_id

    def get_daily_digest(self, user_id: str, digest_date: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM daily_digests
                WHERE user_id = ? AND digest_date = ?
                """,
                (user_id, digest_date),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = self._parse_json_value(data.get("payload"), {})
        return data

    # =========================================================================
    # v2 Agent trust methods
    # =========================================================================

    def get_agent_trust(self, user_id: str, agent_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM agent_trust
                WHERE user_id = ? AND agent_id = ?
                """,
                (user_id, agent_id),
            ).fetchone()
        if row:
            return dict(row)
        return {
            "user_id": user_id,
            "agent_id": agent_id,
            "total_proposals": 0,
            "approved_proposals": 0,
            "rejected_proposals": 0,
            "auto_stashed_proposals": 0,
            "last_proposed_at": None,
            "last_approved_at": None,
            "trust_score": 0.0,
        }

    @staticmethod
    def _compute_trust_score(
        *,
        total_proposals: int,
        approved_proposals: int,
        last_approved_at: Optional[str],
    ) -> float:
        approval_rate = approved_proposals / total_proposals if total_proposals > 0 else 0.0
        recency_score = 0.0
        if last_approved_at:
            try:
                approved_dt = datetime.fromisoformat(last_approved_at)
                days_since = max(
                    0.0,
                    (datetime.utcnow() - approved_dt).total_seconds() / 86400.0,
                )
                recency_score = max(0.0, 1.0 - min(days_since, 30.0) / 30.0)
            except Exception:
                recency_score = 0.0
        return round((approval_rate * 0.7) + (recency_score * 0.3), 4)

    def _upsert_agent_trust_row(
        self,
        *,
        user_id: str,
        agent_id: str,
        total_proposals: int,
        approved_proposals: int,
        rejected_proposals: int,
        auto_stashed_proposals: int,
        last_proposed_at: Optional[str],
        last_approved_at: Optional[str],
    ) -> Dict[str, Any]:
        trust_score = self._compute_trust_score(
            total_proposals=total_proposals,
            approved_proposals=approved_proposals,
            last_approved_at=last_approved_at,
        )
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_trust (
                    user_id, agent_id, total_proposals, approved_proposals, rejected_proposals,
                    auto_stashed_proposals, last_proposed_at, last_approved_at, trust_score, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, agent_id) DO UPDATE SET
                    total_proposals=excluded.total_proposals,
                    approved_proposals=excluded.approved_proposals,
                    rejected_proposals=excluded.rejected_proposals,
                    auto_stashed_proposals=excluded.auto_stashed_proposals,
                    last_proposed_at=excluded.last_proposed_at,
                    last_approved_at=excluded.last_approved_at,
                    trust_score=excluded.trust_score,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    agent_id,
                    int(total_proposals),
                    int(approved_proposals),
                    int(rejected_proposals),
                    int(auto_stashed_proposals),
                    last_proposed_at,
                    last_approved_at,
                    trust_score,
                    datetime.utcnow().isoformat(),
                ),
            )
        return self.get_agent_trust(user_id=user_id, agent_id=agent_id)

    def record_agent_proposal(self, user_id: str, agent_id: Optional[str], status: str) -> Dict[str, Any]:
        if not user_id or not agent_id:
            return {}
        current = self.get_agent_trust(user_id=user_id, agent_id=agent_id)
        now_iso = datetime.utcnow().isoformat()
        auto_stashed = int(current.get("auto_stashed_proposals", 0))
        if (status or "").upper() == "AUTO_STASHED":
            auto_stashed += 1
        return self._upsert_agent_trust_row(
            user_id=user_id,
            agent_id=agent_id,
            total_proposals=int(current.get("total_proposals", 0)) + 1,
            approved_proposals=int(current.get("approved_proposals", 0)),
            rejected_proposals=int(current.get("rejected_proposals", 0)),
            auto_stashed_proposals=auto_stashed,
            last_proposed_at=now_iso,
            last_approved_at=current.get("last_approved_at"),
        )

    def record_agent_commit_outcome(self, user_id: str, agent_id: Optional[str], outcome: str) -> Dict[str, Any]:
        if not user_id or not agent_id:
            return {}
        current = self.get_agent_trust(user_id=user_id, agent_id=agent_id)
        outcome_upper = (outcome or "").upper()
        approved = int(current.get("approved_proposals", 0))
        rejected = int(current.get("rejected_proposals", 0))
        auto_stashed = int(current.get("auto_stashed_proposals", 0))
        last_approved_at = current.get("last_approved_at")
        now_iso = datetime.utcnow().isoformat()
        if outcome_upper == "APPROVED":
            approved += 1
            last_approved_at = now_iso
        elif outcome_upper == "REJECTED":
            rejected += 1
        elif outcome_upper == "AUTO_STASHED":
            auto_stashed += 1
        return self._upsert_agent_trust_row(
            user_id=user_id,
            agent_id=agent_id,
            total_proposals=int(current.get("total_proposals", 0)),
            approved_proposals=approved,
            rejected_proposals=rejected,
            auto_stashed_proposals=auto_stashed,
            last_proposed_at=current.get("last_proposed_at"),
            last_approved_at=last_approved_at,
        )

    # =========================================================================
    # v2 Namespace methods
    # =========================================================================

    def ensure_namespace(self, user_id: str, name: str, description: Optional[str] = None) -> str:
        ns_name = (name or "default").strip() or "default"
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM namespaces WHERE user_id = ? AND name = ?
                """,
                (user_id, ns_name),
            ).fetchone()
            if row:
                namespace_id = row["id"]
                conn.execute(
                    """
                    UPDATE namespaces
                    SET description = COALESCE(?, description), updated_at = ?
                    WHERE id = ?
                    """,
                    (description, datetime.utcnow().isoformat(), namespace_id),
                )
                return namespace_id
            namespace_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO namespaces (id, user_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    namespace_id,
                    user_id,
                    ns_name,
                    description,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            return namespace_id

    def list_namespaces(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM namespaces WHERE 1=1"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY created_at ASC"
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def grant_namespace_permission(
        self,
        *,
        user_id: str,
        agent_id: str,
        namespace: str,
        capability: str = "read",
        expires_at: Optional[str] = None,
    ) -> str:
        namespace_id = self.ensure_namespace(user_id=user_id, name=namespace)
        permission_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO namespace_permissions (
                    id, namespace_id, user_id, agent_id, capability, granted_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(namespace_id, user_id, agent_id, capability) DO UPDATE SET
                    expires_at=excluded.expires_at,
                    granted_at=excluded.granted_at
                """,
                (
                    permission_id,
                    namespace_id,
                    user_id,
                    agent_id,
                    capability,
                    datetime.utcnow().isoformat(),
                    expires_at,
                ),
            )
        return permission_id

    def list_namespace_permissions(
        self,
        *,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        namespace: Optional[str] = None,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT p.*, n.name AS namespace_name
            FROM namespace_permissions p
            JOIN namespaces n ON n.id = p.namespace_id
            WHERE 1=1
        """
        params: List[Any] = []
        if user_id:
            query += " AND p.user_id = ?"
            params.append(user_id)
        if agent_id:
            query += " AND p.agent_id = ?"
            params.append(agent_id)
        if namespace:
            query += " AND n.name = ?"
            params.append(namespace)
        if not include_expired:
            query += " AND (p.expires_at IS NULL OR p.expires_at > ?)"
            params.append(datetime.utcnow().isoformat())
        query += " ORDER BY p.granted_at DESC"
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def get_agent_allowed_namespaces(self, user_id: str, agent_id: Optional[str], capability: str = "read") -> List[str]:
        # User-local or missing agent context falls back to default namespace.
        if not agent_id:
            return ["default"]
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT n.name AS namespace_name
                FROM namespace_permissions p
                JOIN namespaces n ON n.id = p.namespace_id
                WHERE p.user_id = ?
                  AND p.agent_id IN (?, '*')
                  AND p.capability IN (?, '*')
                  AND (p.expires_at IS NULL OR p.expires_at > ?)
                """,
                (user_id, agent_id, capability, datetime.utcnow().isoformat()),
            ).fetchall()
        namespaces = [str(row["namespace_name"]) for row in rows if row["namespace_name"]]
        if "default" not in namespaces:
            namespaces.append("default")
        return sorted(set(namespaces))

    # =========================================================================
    # v2 Agent policy methods
    # =========================================================================

    def upsert_agent_policy(
        self,
        *,
        user_id: str,
        agent_id: str,
        allowed_confidentiality_scopes: Optional[List[str]] = None,
        allowed_capabilities: Optional[List[str]] = None,
        allowed_namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        policy_id = str(uuid.uuid4())
        scopes = sorted({
            str(scope).strip().lower()
            for scope in (allowed_confidentiality_scopes or [])
            if str(scope).strip()
        })
        capabilities = sorted({
            str(capability).strip().lower()
            for capability in (allowed_capabilities or [])
            if str(capability).strip()
        })
        namespaces = sorted({
            str(namespace).strip()
            for namespace in (allowed_namespaces or [])
            if str(namespace).strip()
        })
        now_iso = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO agent_policies (
                    id,
                    user_id,
                    agent_id,
                    allowed_confidentiality_scopes,
                    allowed_capabilities,
                    allowed_namespaces,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, agent_id) DO UPDATE SET
                    allowed_confidentiality_scopes=excluded.allowed_confidentiality_scopes,
                    allowed_capabilities=excluded.allowed_capabilities,
                    allowed_namespaces=excluded.allowed_namespaces,
                    updated_at=excluded.updated_at
                """,
                (
                    policy_id,
                    user_id,
                    agent_id,
                    json.dumps(scopes),
                    json.dumps(capabilities),
                    json.dumps(namespaces),
                    now_iso,
                    now_iso,
                ),
            )
        policy = self.get_agent_policy(user_id=user_id, agent_id=agent_id, include_wildcard=False)
        return policy or {
            "id": policy_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "allowed_confidentiality_scopes": scopes,
            "allowed_capabilities": capabilities,
            "allowed_namespaces": namespaces,
        }

    def get_agent_policy(
        self,
        *,
        user_id: str,
        agent_id: str,
        include_wildcard: bool = True,
    ) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            if include_wildcard:
                row = conn.execute(
                    """
                    SELECT *,
                           CASE WHEN agent_id = ? THEN 0 ELSE 1 END AS _priority
                    FROM agent_policies
                    WHERE user_id = ?
                      AND agent_id IN (?, '*')
                    ORDER BY _priority ASC
                    LIMIT 1
                    """,
                    (agent_id, user_id, agent_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT * FROM agent_policies
                    WHERE user_id = ? AND agent_id = ?
                    LIMIT 1
                    """,
                    (user_id, agent_id),
                ).fetchone()

        if not row:
            return None

        data = dict(row)
        data["allowed_confidentiality_scopes"] = self._parse_json_value(data.get("allowed_confidentiality_scopes"), [])
        data["allowed_capabilities"] = self._parse_json_value(data.get("allowed_capabilities"), [])
        data["allowed_namespaces"] = self._parse_json_value(data.get("allowed_namespaces"), [])
        if include_wildcard:
            data["policy_scope"] = "exact" if data.get("agent_id") == agent_id else "wildcard"
        data.pop("_priority", None)
        return data

    def list_agent_policies(self, *, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM agent_policies WHERE 1=1"
        params: List[Any] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY user_id ASC, agent_id ASC"
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        policies: List[Dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["allowed_confidentiality_scopes"] = self._parse_json_value(data.get("allowed_confidentiality_scopes"), [])
            data["allowed_capabilities"] = self._parse_json_value(data.get("allowed_capabilities"), [])
            data["allowed_namespaces"] = self._parse_json_value(data.get("allowed_namespaces"), [])
            policies.append(data)
        return policies

    def delete_agent_policy(self, *, user_id: str, agent_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM agent_policies
                WHERE user_id = ? AND agent_id = ?
                """,
                (user_id, agent_id),
            )
        return cursor.rowcount > 0

    def list_user_ids(self) -> List[str]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT user_id FROM (
                    SELECT user_id FROM memories
                    UNION ALL
                    SELECT user_id FROM sessions
                    UNION ALL
                    SELECT user_id FROM proposal_commits
                    UNION ALL
                    SELECT user_id FROM handoff_sessions
                    UNION ALL
                    SELECT user_id FROM handoff_lanes
                )
                WHERE user_id IS NOT NULL AND user_id != ''
                ORDER BY user_id
                """
            ).fetchall()
        return [str(row["user_id"]) for row in rows if row["user_id"]]

    # =========================================================================
    # v2 Invariant methods
    # =========================================================================

    def upsert_invariant(
        self,
        user_id: str,
        invariant_key: str,
        invariant_value: str,
        category: str = "identity",
        confidence: float = 0.7,
        source_memory_id: Optional[str] = None,
    ) -> str:
        invariant_id = str(uuid.uuid4())
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO invariants (
                    id, user_id, invariant_key, invariant_value, category, confidence, source_memory_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, invariant_key) DO UPDATE SET
                    invariant_value=excluded.invariant_value,
                    category=excluded.category,
                    confidence=excluded.confidence,
                    source_memory_id=excluded.source_memory_id,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    invariant_id,
                    user_id,
                    invariant_key,
                    invariant_value,
                    category,
                    confidence,
                    source_memory_id,
                ),
            )
        return invariant_id

    def get_invariant(self, user_id: str, invariant_key: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM invariants
                WHERE user_id = ? AND invariant_key = ?
                """,
                (user_id, invariant_key),
            ).fetchone()
        return dict(row) if row else None

    def list_invariants(self, user_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM invariants
                WHERE user_id = ?
                ORDER BY confidence DESC, updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    # =========================================================================
    # Dashboard / Visualization methods
    # =========================================================================

    def get_constellation_data(self, user_id: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
        """Build graph data for the constellation visualizer."""
        with self._get_connection() as conn:
            # Nodes: memories
            mem_query = "SELECT id, memory, strength, layer, categories, created_at FROM memories WHERE tombstone = 0"
            params: List[Any] = []
            if user_id:
                mem_query += " AND user_id = ?"
                params.append(user_id)
            mem_query += " ORDER BY strength DESC LIMIT ?"
            params.append(limit)
            mem_rows = conn.execute(mem_query, params).fetchall()

            nodes = []
            node_ids = set()
            for row in mem_rows:
                cats = row["categories"]
                if cats:
                    try:
                        cats = json.loads(cats)
                    except Exception:
                        cats = []
                else:
                    cats = []
                nodes.append({
                    "id": row["id"],
                    "memory": (row["memory"] or "")[:120],
                    "strength": row["strength"],
                    "layer": row["layer"],
                    "categories": cats,
                    "created_at": row["created_at"],
                })
                node_ids.add(row["id"])

            # Edges from scene_memories (memories sharing a scene)
            edges: List[Dict[str, Any]] = []
            if node_ids:
                placeholders = ",".join("?" for _ in node_ids)
                scene_rows = conn.execute(
                    f"""
                    SELECT a.memory_id AS source, b.memory_id AS target, a.scene_id
                    FROM scene_memories a
                    JOIN scene_memories b ON a.scene_id = b.scene_id AND a.memory_id < b.memory_id
                    WHERE a.memory_id IN ({placeholders}) AND b.memory_id IN ({placeholders})
                    """,
                    list(node_ids) + list(node_ids),
                ).fetchall()
                for row in scene_rows:
                    edges.append({"source": row["source"], "target": row["target"], "type": "scene"})

                # Edges from profile_memories (memories sharing a profile)
                profile_rows = conn.execute(
                    f"""
                    SELECT a.memory_id AS source, b.memory_id AS target, a.profile_id
                    FROM profile_memories a
                    JOIN profile_memories b ON a.profile_id = b.profile_id AND a.memory_id < b.memory_id
                    WHERE a.memory_id IN ({placeholders}) AND b.memory_id IN ({placeholders})
                    """,
                    list(node_ids) + list(node_ids),
                ).fetchall()
                for row in profile_rows:
                    edges.append({"source": row["source"], "target": row["target"], "type": "profile"})

        return {"nodes": nodes, "edges": edges}

    def get_decay_log_entries(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent decay log entries for the dashboard sparkline."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM decay_log ORDER BY run_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # =========================================================================
    # Handoff session methods (legacy compatibility)
    # =========================================================================

    def add_handoff_session(self, data: Dict[str, Any]) -> str:
        session_id = data.get("id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO handoff_sessions (
                    id, user_id, agent_id, repo, repo_id, status, task_summary,
                    decisions_made, files_touched, todos_remaining, blockers, key_commands, test_results,
                    context_snapshot, linked_memory_ids, linked_scene_ids, lane_id,
                    started_at, ended_at, last_checkpoint_at,
                    namespace, confidentiality_scope,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    data.get("user_id", "default"),
                    data.get("agent_id", "unknown"),
                    data.get("repo"),
                    data.get("repo_id"),
                    data.get("status", "paused"),
                    data.get("task_summary", ""),
                    json.dumps(data.get("decisions_made", [])),
                    json.dumps(data.get("files_touched", [])),
                    json.dumps(data.get("todos_remaining", [])),
                    json.dumps(data.get("blockers", [])),
                    json.dumps(data.get("key_commands", [])),
                    json.dumps(data.get("test_results", [])),
                    data.get("context_snapshot"),
                    json.dumps(data.get("linked_memory_ids", [])),
                    json.dumps(data.get("linked_scene_ids", [])),
                    data.get("lane_id"),
                    data.get("started_at", now),
                    data.get("ended_at"),
                    data.get("last_checkpoint_at", data.get("updated_at", now)),
                    data.get("namespace", "default"),
                    data.get("confidentiality_scope", "work"),
                    data.get("created_at", now),
                    data.get("updated_at", now),
                ),
            )
        return session_id

    def get_handoff_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM handoff_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row:
                return self._handoff_row_to_dict(row)
        return None

    def get_last_handoff_session(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        repo: Optional[str] = None,
        repo_id: Optional[str] = None,
        statuses: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        query = "SELECT * FROM handoff_sessions WHERE user_id = ?"
        params: List[Any] = [user_id]
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if repo_id:
            query += " AND repo_id = ?"
            params.append(repo_id)
        elif repo:
            query += " AND repo = ?"
            params.append(repo)
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" AND status IN ({placeholders})"
            params.extend(statuses)
        query += " ORDER BY COALESCE(last_checkpoint_at, updated_at, created_at) DESC, created_at DESC LIMIT 1"
        with self._get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            if row:
                return self._handoff_row_to_dict(row)
        return None

    def list_handoff_sessions(
        self,
        user_id: str,
        agent_id: Optional[str] = None,
        repo: Optional[str] = None,
        repo_id: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM handoff_sessions WHERE user_id = ?"
        params: List[Any] = [user_id]
        if agent_id:
            query += " AND agent_id = ?"
            params.append(agent_id)
        if repo_id:
            query += " AND repo_id = ?"
            params.append(repo_id)
        elif repo:
            query += " AND repo = ?"
            params.append(repo)
        if status:
            query += " AND status = ?"
            params.append(status)
        elif statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" AND status IN ({placeholders})"
            params.extend(statuses)
        query += " ORDER BY COALESCE(last_checkpoint_at, updated_at, created_at) DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._handoff_row_to_dict(row) for row in rows]

    def update_handoff_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        set_clauses = []
        params: List[Any] = []
        json_fields = {
            "decisions_made",
            "files_touched",
            "todos_remaining",
            "blockers",
            "key_commands",
            "test_results",
            "linked_memory_ids",
            "linked_scene_ids",
        }
        for key, value in updates.items():
            if key in json_fields:
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)
        if not set_clauses:
            return False
        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        params.append(session_id)
        with self._get_connection() as conn:
            cursor = conn.execute(
                f"UPDATE handoff_sessions SET {', '.join(set_clauses)} WHERE id = ?",
                params,
            )
            return cursor.rowcount > 0

    def delete_handoff_sessions(self, session_ids: List[str]) -> int:
        ids = [str(value) for value in (session_ids or []) if str(value).strip()]
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._get_connection() as conn:
            conn.execute(
                f"DELETE FROM handoff_session_memories WHERE session_id IN ({placeholders})",
                ids,
            )
            cursor = conn.execute(
                f"DELETE FROM handoff_sessions WHERE id IN ({placeholders})",
                ids,
            )
            return cursor.rowcount

    def prune_handoff_sessions(self, user_id: str, max_sessions: int) -> int:
        limit_value = max(0, int(max_sessions))
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id FROM handoff_sessions
                WHERE user_id = ?
                ORDER BY COALESCE(last_checkpoint_at, updated_at, created_at) DESC, created_at DESC
                """,
                (user_id,),
            ).fetchall()
        session_ids = [str(row["id"]) for row in rows]
        stale_ids = session_ids[limit_value:]
        return self.delete_handoff_sessions(stale_ids)

    def add_handoff_session_memory(self, session_id: str, memory_id: str, relevance_score: float = 1.0) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO handoff_session_memories (session_id, memory_id, relevance_score) VALUES (?, ?, ?)",
                (session_id, memory_id, relevance_score),
            )

    def get_handoff_session_memories(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT m.*, hsm.relevance_score FROM memories m
                JOIN handoff_session_memories hsm ON m.id = hsm.memory_id
                WHERE hsm.session_id = ? AND m.tombstone = 0
                ORDER BY hsm.relevance_score DESC
                """,
                (session_id,),
            ).fetchall()
            return [self._row_to_dict(row) for row in rows]

    # =========================================================================
    # Handoff lane + checkpoint methods (session bus)
    # =========================================================================

    def add_handoff_lane(self, data: Dict[str, Any]) -> str:
        lane_id = data.get("id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO handoff_lanes (
                    id, user_id, repo_id, repo_path, branch, lane_type, status,
                    objective, current_state, namespace, confidentiality_scope,
                    last_checkpoint_at, version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lane_id,
                    data.get("user_id", "default"),
                    data.get("repo_id"),
                    data.get("repo_path"),
                    data.get("branch"),
                    data.get("lane_type", "general"),
                    data.get("status", "active"),
                    data.get("objective"),
                    json.dumps(data.get("current_state", {})),
                    data.get("namespace", "default"),
                    data.get("confidentiality_scope", "work"),
                    data.get("last_checkpoint_at", now),
                    int(data.get("version", 0)),
                    data.get("created_at", now),
                    data.get("updated_at", now),
                ),
            )
        return lane_id

    def get_handoff_lane(self, lane_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM handoff_lanes WHERE id = ?",
                (lane_id,),
            ).fetchone()
            if not row:
                return None
            return self._handoff_lane_row_to_dict(row)

    def list_handoff_lanes(
        self,
        user_id: str,
        *,
        repo_id: Optional[str] = None,
        status: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM handoff_lanes WHERE user_id = ?"
        params: List[Any] = [user_id]
        if repo_id:
            query += " AND repo_id = ?"
            params.append(repo_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        elif statuses:
            placeholders = ", ".join("?" for _ in statuses)
            query += f" AND status IN ({placeholders})"
            params.extend(statuses)
        query += " ORDER BY COALESCE(last_checkpoint_at, created_at) DESC, created_at DESC LIMIT ?"
        params.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._handoff_lane_row_to_dict(row) for row in rows]

    def update_handoff_lane(
        self,
        lane_id: str,
        updates: Dict[str, Any],
        *,
        expected_version: Optional[int] = None,
    ) -> bool:
        set_clauses = []
        params: List[Any] = []
        for key, value in updates.items():
            if key == "current_state" and not isinstance(value, str):
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)
        if not set_clauses:
            return False
        set_clauses.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        query = f"UPDATE handoff_lanes SET {', '.join(set_clauses)} WHERE id = ?"
        params.append(lane_id)
        if expected_version is not None:
            query += " AND version = ?"
            params.append(int(expected_version))
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.rowcount > 0

    def delete_handoff_lanes(self, lane_ids: List[str]) -> int:
        ids = [str(value) for value in (lane_ids or []) if str(value).strip()]
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._get_connection() as conn:
            checkpoint_rows = conn.execute(
                f"SELECT id FROM handoff_checkpoints WHERE lane_id IN ({placeholders})",
                ids,
            ).fetchall()
            checkpoint_ids = [str(row["id"]) for row in checkpoint_rows]
        if checkpoint_ids:
            self.delete_handoff_checkpoints(checkpoint_ids)
        with self._get_connection() as conn:
            conn.execute(
                f"DELETE FROM handoff_lane_conflicts WHERE lane_id IN ({placeholders})",
                ids,
            )
            cursor = conn.execute(
                f"DELETE FROM handoff_lanes WHERE id IN ({placeholders})",
                ids,
            )
            return cursor.rowcount

    def prune_handoff_lanes(self, user_id: str, max_lanes: int) -> int:
        limit_value = max(0, int(max_lanes))
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id FROM handoff_lanes
                WHERE user_id = ?
                ORDER BY COALESCE(last_checkpoint_at, created_at) DESC, created_at DESC
                """,
                (user_id,),
            ).fetchall()
        lane_ids = [str(row["id"]) for row in rows]
        stale_ids = lane_ids[limit_value:]
        return self.delete_handoff_lanes(stale_ids)

    def add_handoff_checkpoint(self, data: Dict[str, Any]) -> str:
        checkpoint_id = data.get("id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO handoff_checkpoints (
                    id, lane_id, user_id, agent_id, agent_role, event_type, task_summary,
                    decisions_made, files_touched, todos_remaining, blockers, key_commands,
                    test_results, merge_conflicts, context_snapshot, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint_id,
                    data.get("lane_id"),
                    data.get("user_id", "default"),
                    data.get("agent_id", "unknown"),
                    data.get("agent_role"),
                    data.get("event_type", "tool_complete"),
                    data.get("task_summary"),
                    json.dumps(data.get("decisions_made", [])),
                    json.dumps(data.get("files_touched", [])),
                    json.dumps(data.get("todos_remaining", [])),
                    json.dumps(data.get("blockers", [])),
                    json.dumps(data.get("key_commands", [])),
                    json.dumps(data.get("test_results", [])),
                    json.dumps(data.get("merge_conflicts", [])),
                    data.get("context_snapshot"),
                    data.get("created_at", now),
                ),
            )
        return checkpoint_id

    def get_handoff_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM handoff_checkpoints WHERE id = ?",
                (checkpoint_id,),
            ).fetchone()
            if not row:
                return None
            return self._handoff_checkpoint_row_to_dict(row)

    def list_handoff_checkpoints(self, lane_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM handoff_checkpoints
                WHERE lane_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (lane_id, max(1, int(limit))),
            ).fetchall()
        return [self._handoff_checkpoint_row_to_dict(row) for row in rows]

    def get_latest_handoff_checkpoint(self, lane_id: str) -> Optional[Dict[str, Any]]:
        checkpoints = self.list_handoff_checkpoints(lane_id=lane_id, limit=1)
        return checkpoints[0] if checkpoints else None

    def delete_handoff_checkpoints(self, checkpoint_ids: List[str]) -> int:
        ids = [str(value) for value in (checkpoint_ids or []) if str(value).strip()]
        if not ids:
            return 0
        placeholders = ", ".join("?" for _ in ids)
        with self._get_connection() as conn:
            conn.execute(
                f"DELETE FROM handoff_checkpoint_memories WHERE checkpoint_id IN ({placeholders})",
                ids,
            )
            conn.execute(
                f"DELETE FROM handoff_checkpoint_scenes WHERE checkpoint_id IN ({placeholders})",
                ids,
            )
            conn.execute(
                f"DELETE FROM handoff_lane_conflicts WHERE checkpoint_id IN ({placeholders})",
                ids,
            )
            cursor = conn.execute(
                f"DELETE FROM handoff_checkpoints WHERE id IN ({placeholders})",
                ids,
            )
            return cursor.rowcount

    def prune_handoff_checkpoints(self, lane_id: str, max_checkpoints: int) -> int:
        limit_value = max(0, int(max_checkpoints))
        checkpoints = self.list_handoff_checkpoints(lane_id=lane_id, limit=100000)
        stale_ids = [checkpoint["id"] for checkpoint in checkpoints[limit_value:]]
        return self.delete_handoff_checkpoints(stale_ids)

    def add_handoff_checkpoint_memory(
        self,
        checkpoint_id: str,
        memory_id: str,
        relevance_score: float = 1.0,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO handoff_checkpoint_memories (checkpoint_id, memory_id, relevance_score)
                VALUES (?, ?, ?)
                """,
                (checkpoint_id, memory_id, relevance_score),
            )

    def add_handoff_checkpoint_scene(
        self,
        checkpoint_id: str,
        scene_id: str,
        relevance_score: float = 1.0,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO handoff_checkpoint_scenes (checkpoint_id, scene_id, relevance_score)
                VALUES (?, ?, ?)
                """,
                (checkpoint_id, scene_id, relevance_score),
            )

    def get_handoff_checkpoint_memories(self, checkpoint_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT m.*, hcm.relevance_score FROM memories m
                JOIN handoff_checkpoint_memories hcm ON m.id = hcm.memory_id
                WHERE hcm.checkpoint_id = ? AND m.tombstone = 0
                ORDER BY hcm.relevance_score DESC
                """,
                (checkpoint_id,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_handoff_checkpoint_scenes(self, checkpoint_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.*, hcs.relevance_score FROM scenes s
                JOIN handoff_checkpoint_scenes hcs ON s.id = hcs.scene_id
                WHERE hcs.checkpoint_id = ? AND s.tombstone = 0
                ORDER BY hcs.relevance_score DESC
                """,
                (checkpoint_id,),
            ).fetchall()
        return [self._scene_row_to_dict(row) for row in rows]

    def add_handoff_lane_conflict(self, data: Dict[str, Any]) -> str:
        conflict_id = data.get("id", str(uuid.uuid4()))
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO handoff_lane_conflicts (
                    id, lane_id, checkpoint_id, user_id,
                    conflict_fields, previous_state, incoming_state, resolved_state, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conflict_id,
                    data.get("lane_id"),
                    data.get("checkpoint_id"),
                    data.get("user_id", "default"),
                    json.dumps(data.get("conflict_fields", [])),
                    json.dumps(data.get("previous_state", {})),
                    json.dumps(data.get("incoming_state", {})),
                    json.dumps(data.get("resolved_state", {})),
                    data.get("created_at", now),
                ),
            )
        return conflict_id

    def list_handoff_lane_conflicts(self, lane_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM handoff_lane_conflicts
                WHERE lane_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (lane_id, max(1, int(limit))),
            ).fetchall()
        return [self._handoff_conflict_row_to_dict(row) for row in rows]

    def _handoff_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        for key in {
            "decisions_made",
            "files_touched",
            "todos_remaining",
            "blockers",
            "key_commands",
            "test_results",
            "linked_memory_ids",
            "linked_scene_ids",
        }:
            data[key] = self._parse_json_value(data.get(key), [])
        data["repo_id"] = data.get("repo_id") or data.get("repo")
        data["namespace"] = data.get("namespace") or "default"
        data["confidentiality_scope"] = data.get("confidentiality_scope") or "work"
        data["last_checkpoint_at"] = data.get("last_checkpoint_at") or data.get("updated_at") or data.get("created_at")
        return data

    def _handoff_lane_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["current_state"] = self._parse_json_value(data.get("current_state"), {})
        data["namespace"] = data.get("namespace") or "default"
        data["confidentiality_scope"] = data.get("confidentiality_scope") or "work"
        data["version"] = int(data.get("version", 0) or 0)
        return data

    def _handoff_checkpoint_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        for key in {
            "decisions_made",
            "files_touched",
            "todos_remaining",
            "blockers",
            "key_commands",
            "test_results",
            "merge_conflicts",
        }:
            data[key] = self._parse_json_value(data.get(key), [])
        return data

    def _handoff_conflict_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["conflict_fields"] = self._parse_json_value(data.get("conflict_fields"), [])
        data["previous_state"] = self._parse_json_value(data.get("previous_state"), {})
        data["incoming_state"] = self._parse_json_value(data.get("incoming_state"), {})
        data["resolved_state"] = self._parse_json_value(data.get("resolved_state"), {})
        return data

    # =========================================================================
    # Utilities
    # =========================================================================

    @staticmethod
    def _parse_json_value(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except Exception:
            return default
