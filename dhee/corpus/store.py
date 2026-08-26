"""Where a corpus lives on disk, and why it lives apart from belief memory.

Dhee's memory is a store of *beliefs* — things that are true about the user and the
work. Its quality pipeline is tuned to keep documents out: `dhee/memory/quality.py`
classifies `doc_chunk` and anything carrying a `source_path` as artifact-like rather
than belief, and `handoff_snapshot` treats those kinds as noise. That was the right
call. A thousand chunks of a PDF are not a thousand new beliefs, and letting them in is
what made memory noisy before.

So a corpus gets its own tables and its own vector collection. Nothing here is ever
admitted into memory, nothing here is scored by the belief pipeline, and the two can
never contaminate each other. That separation is the entire reason this is a third lane
rather than a new metadata kind on the old one.

The schema is content-addressed throughout, which is what makes re-indexing cheap:

- ``blobs``, ``pages`` and ``chunks`` are keyed by the sha256 of the file's bytes and
  are **not** scoped to a corpus. Extraction and chunking of a given piece of content
  happen once on this machine, however many folders it appears in.
- ``docs`` is the only corpus-scoped table: it maps ``(corpus, path) -> blob``. A file
  that moves rewrites one row here and touches nothing else.
- ``embedded`` records which chunks already have a vector under which model, so a
  re-index never pays a metered embedding call twice for the same content.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from dhee.corpus.extract import Chunk, ExtractedDoc, ExtractedPage, ExtractedLine
from dhee.corpus.tree import BlobEntry, FolderSnapshot, TreeNode

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS corpus_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corpora (
    corpus_id       TEXT PRIMARY KEY,
    root_path       TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    root_sha        TEXT NOT NULL DEFAULT '',
    embedder_model  TEXT NOT NULL DEFAULT '',
    embedding_dims  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'new',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    last_error      TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_corpora_root ON corpora(root_path);

-- Content-addressed and corpus-independent: extraction happens once per blob, ever.
CREATE TABLE IF NOT EXISTS blobs (
    blob_sha           TEXT PRIMARY KEY,
    size_bytes         INTEGER NOT NULL DEFAULT 0,
    extraction_status  TEXT NOT NULL DEFAULT '',
    extraction_engine  TEXT NOT NULL DEFAULT '',
    extraction_error   TEXT NOT NULL DEFAULT '',
    page_count         INTEGER NOT NULL DEFAULT 0,
    was_scanned        INTEGER NOT NULL DEFAULT 0,
    extracted_at       REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pages (
    blob_sha  TEXT NOT NULL,
    page_no   INTEGER NOT NULL,
    text      TEXT NOT NULL DEFAULT '',
    lines     TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (blob_sha, page_no)
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id    TEXT PRIMARY KEY,
    blob_sha    TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    page_no     INTEGER NOT NULL DEFAULT 0,
    text        TEXT NOT NULL,
    char_start  INTEGER NOT NULL DEFAULT 0,
    char_end    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chunks_blob ON chunks(blob_sha, chunk_index);

-- Which chunks already have a vector, under which model. The guard against paying
-- twice for the same embedding.
CREATE TABLE IF NOT EXISTS embedded (
    chunk_id    TEXT NOT NULL,
    model       TEXT NOT NULL,
    corpus_id   TEXT NOT NULL,
    embedded_at REAL NOT NULL,
    PRIMARY KEY (chunk_id, model, corpus_id)
);

-- The only corpus-scoped table. A rename rewrites exactly one row.
CREATE TABLE IF NOT EXISTS docs (
    corpus_id     TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    blob_sha      TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    mtime_ns      INTEGER NOT NULL DEFAULT 0,
    indexed_at    REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (corpus_id, relative_path)
);
CREATE INDEX IF NOT EXISTS idx_docs_blob ON docs(corpus_id, blob_sha);

-- The previous scan, kept so the next one can trust the stat cache.
CREATE TABLE IF NOT EXISTS snapshots (
    corpus_id TEXT PRIMARY KEY,
    root_sha  TEXT NOT NULL,
    payload   TEXT NOT NULL,
    taken_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS skipped (
    corpus_id     TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    reason        TEXT NOT NULL,
    PRIMARY KEY (corpus_id, relative_path)
);
"""


@dataclass(frozen=True, slots=True)
class CorpusRecord:
    corpus_id: str
    root_path: str
    label: str
    root_sha: str
    embedder_model: str
    embedding_dims: int
    status: str
    created_at: float
    updated_at: float
    last_error: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "root_path": self.root_path,
            "label": self.label,
            "root_sha": self.root_sha,
            "embedder_model": self.embedder_model,
            "embedding_dims": self.embedding_dims,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_error": self.last_error,
        }


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    """A chunk plus where it can be found — everything a citation needs."""

    chunk_id: str
    blob_sha: str
    chunk_index: int
    page_no: int
    text: str
    relative_path: str = ""
    char_start: int = 0
    char_end: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "blob_sha": self.blob_sha,
            "chunk_index": self.chunk_index,
            "page_no": self.page_no,
            "text": self.text,
            "relative_path": self.relative_path,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }


class CorpusStore:
    """SQLite behind a small typed surface. One connection, guarded by one lock."""

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._lock = threading.RLock()
        self._migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _migrate(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.execute(
                "INSERT OR REPLACE INTO corpus_meta(key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self._conn.commit()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ---------------------------------------------------------------- corpora

    def upsert_corpus(
        self,
        *,
        corpus_id: str,
        root_path: str,
        label: str = "",
        embedder_model: str = "",
        embedding_dims: int = 0,
    ) -> CorpusRecord:
        now = time.time()
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO corpora
                       (corpus_id, root_path, label, embedder_model, embedding_dims, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(corpus_id) DO UPDATE SET
                       root_path=excluded.root_path,
                       label=excluded.label,
                       embedder_model=excluded.embedder_model,
                       embedding_dims=excluded.embedding_dims,
                       updated_at=excluded.updated_at""",
                (corpus_id, root_path, label, embedder_model, embedding_dims, now, now),
            )
        record = self.get_corpus(corpus_id)
        assert record is not None
        return record

    def get_corpus(self, corpus_id: str) -> Optional[CorpusRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM corpora WHERE corpus_id = ?", (corpus_id,)
            ).fetchone()
        return _corpus_from_row(row) if row else None

    def get_corpus_by_root(self, root_path: str) -> Optional[CorpusRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM corpora WHERE root_path = ?", (root_path,)
            ).fetchone()
        return _corpus_from_row(row) if row else None

    def list_corpora(self) -> List[CorpusRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM corpora ORDER BY label, root_path").fetchall()
        return [_corpus_from_row(row) for row in rows]

    def set_corpus_state(
        self,
        corpus_id: str,
        *,
        status: Optional[str] = None,
        root_sha: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> None:
        sets = ["updated_at = ?"]
        params: List[Any] = [time.time()]
        for column, value in (("status", status), ("root_sha", root_sha), ("last_error", last_error)):
            if value is not None:
                sets.append(f"{column} = ?")
                params.append(value)
        params.append(corpus_id)
        with self._tx() as conn:
            conn.execute(f"UPDATE corpora SET {', '.join(sets)} WHERE corpus_id = ?", params)

    def delete_corpus(self, corpus_id: str) -> None:
        """Forget a folder. Blobs and chunks stay: another corpus may share them."""
        with self._tx() as conn:
            for table in ("docs", "skipped", "snapshots", "embedded"):
                conn.execute(f"DELETE FROM {table} WHERE corpus_id = ?", (corpus_id,))
            conn.execute("DELETE FROM corpora WHERE corpus_id = ?", (corpus_id,))

    # ----------------------------------------------------------------- blobs

    def blob_is_extracted(self, blob_sha: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM blobs WHERE blob_sha = ? AND extracted_at > 0", (blob_sha,)
            ).fetchone()
        return row is not None

    def get_blob(self, blob_sha: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM blobs WHERE blob_sha = ?", (blob_sha,)).fetchone()
        return dict(row) if row else None

    def save_extraction(self, *, blob_sha: str, size_bytes: int, doc: ExtractedDoc) -> None:
        """Record what a file yielded, including that it yielded nothing.

        Failures are stored, not dropped. A blob that failed extraction must not be
        retried on every scan, and "why is this document not searchable" needs the
        reason to still be there when someone asks.
        """
        now = time.time()
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO blobs
                       (blob_sha, size_bytes, extraction_status, extraction_engine,
                        extraction_error, page_count, was_scanned, extracted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(blob_sha) DO UPDATE SET
                       size_bytes=excluded.size_bytes,
                       extraction_status=excluded.extraction_status,
                       extraction_engine=excluded.extraction_engine,
                       extraction_error=excluded.extraction_error,
                       page_count=excluded.page_count,
                       was_scanned=excluded.was_scanned,
                       extracted_at=excluded.extracted_at""",
                (
                    blob_sha,
                    size_bytes,
                    doc.status,
                    doc.engine,
                    doc.error,
                    doc.page_count,
                    1 if doc.was_scanned else 0,
                    now,
                ),
            )
            conn.execute("DELETE FROM pages WHERE blob_sha = ?", (blob_sha,))
            conn.executemany(
                "INSERT INTO pages(blob_sha, page_no, text, lines) VALUES (?, ?, ?, ?)",
                [
                    (
                        blob_sha,
                        page.page_no,
                        page.text,
                        json.dumps([_line_as_dict(line) for line in page.lines]),
                    )
                    for page in doc.pages
                ],
            )

    def get_pages(self, blob_sha: str) -> List[ExtractedPage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT page_no, text, lines FROM pages WHERE blob_sha = ? ORDER BY page_no",
                (blob_sha,),
            ).fetchall()
        return [
            ExtractedPage(
                page_no=row["page_no"],
                text=row["text"],
                lines=tuple(_line_from_dict(item) for item in json.loads(row["lines"] or "[]")),
            )
            for row in rows
        ]

    # ---------------------------------------------------------------- chunks

    def save_chunks(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            return
        with self._tx() as conn:
            conn.executemany(
                """INSERT INTO chunks
                       (chunk_id, blob_sha, chunk_index, page_no, text, char_start, char_end)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(chunk_id) DO NOTHING""",
                [
                    (
                        chunk.chunk_id,
                        chunk.blob_sha,
                        chunk.chunk_index,
                        chunk.page_no,
                        chunk.text,
                        chunk.char_start,
                        chunk.char_end,
                    )
                    for chunk in chunks
                ],
            )

    def chunks_for_blob(self, blob_sha: str) -> List[Chunk]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM chunks WHERE blob_sha = ? ORDER BY chunk_index", (blob_sha,)
            ).fetchall()
        return [
            Chunk(
                chunk_id=row["chunk_id"],
                blob_sha=row["blob_sha"],
                chunk_index=row["chunk_index"],
                page_no=row["page_no"],
                text=row["text"],
                char_start=row["char_start"],
                char_end=row["char_end"],
            )
            for row in rows
        ]

    def resolve_chunks(self, corpus_id: str, chunk_ids: Sequence[str]) -> Dict[str, ChunkRecord]:
        """Hydrate chunk ids into citable records, scoped to one corpus.

        The join against ``docs`` is what enforces scoping *and* supplies the path:
        a chunk whose blob is no longer present in this corpus simply does not come
        back, so a deleted file cannot surface in an answer even if its vector is
        still sitting in the collection.
        """
        if not chunk_ids:
            return {}
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT c.*, d.relative_path
                    FROM chunks c
                    JOIN docs d ON d.blob_sha = c.blob_sha AND d.corpus_id = ?
                    WHERE c.chunk_id IN ({placeholders})""",
                (corpus_id, *chunk_ids),
            ).fetchall()

        resolved: Dict[str, ChunkRecord] = {}
        for row in rows:
            existing = resolved.get(row["chunk_id"])
            # A blob can sit at several paths in one corpus; keep the first
            # alphabetically so a citation is stable rather than arbitrary.
            if existing and existing.relative_path <= row["relative_path"]:
                continue
            resolved[row["chunk_id"]] = ChunkRecord(
                chunk_id=row["chunk_id"],
                blob_sha=row["blob_sha"],
                chunk_index=row["chunk_index"],
                page_no=row["page_no"],
                text=row["text"],
                relative_path=row["relative_path"],
                char_start=row["char_start"],
                char_end=row["char_end"],
            )
        return resolved

    # ------------------------------------------------------------- embedding

    def unembedded_chunk_ids(self, corpus_id: str, chunk_ids: Sequence[str], model: str) -> List[str]:
        """The subset that still costs money. Everything else is already paid for."""
        if not chunk_ids:
            return []
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._lock:
            rows = self._conn.execute(
                f"""SELECT chunk_id FROM embedded
                    WHERE model = ? AND corpus_id = ? AND chunk_id IN ({placeholders})""",
                (model, corpus_id, *chunk_ids),
            ).fetchall()
        done = {row["chunk_id"] for row in rows}
        return [chunk_id for chunk_id in chunk_ids if chunk_id not in done]

    def mark_embedded(self, corpus_id: str, chunk_ids: Sequence[str], model: str) -> None:
        if not chunk_ids:
            return
        now = time.time()
        with self._tx() as conn:
            conn.executemany(
                """INSERT INTO embedded(chunk_id, model, corpus_id, embedded_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(chunk_id, model, corpus_id) DO NOTHING""",
                [(chunk_id, model, corpus_id, now) for chunk_id in chunk_ids],
            )

    def forget_embeddings(self, corpus_id: str, chunk_ids: Sequence[str], model: str) -> None:
        if not chunk_ids:
            return
        placeholders = ",".join("?" for _ in chunk_ids)
        with self._tx() as conn:
            conn.execute(
                f"DELETE FROM embedded WHERE corpus_id = ? AND model = ? AND chunk_id IN ({placeholders})",
                (corpus_id, model, *chunk_ids),
            )

    # ------------------------------------------------------------------ docs

    def put_doc(self, corpus_id: str, entry: BlobEntry) -> None:
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO docs(corpus_id, relative_path, blob_sha, size_bytes, mtime_ns, indexed_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(corpus_id, relative_path) DO UPDATE SET
                       blob_sha=excluded.blob_sha,
                       size_bytes=excluded.size_bytes,
                       mtime_ns=excluded.mtime_ns,
                       indexed_at=excluded.indexed_at""",
                (corpus_id, entry.relative_path, entry.blob_sha, entry.size_bytes, entry.mtime_ns, time.time()),
            )

    def move_doc(self, corpus_id: str, old_path: str, new_path: str) -> None:
        """A rename is one UPDATE. No extraction, no chunking, no embedding."""
        with self._tx() as conn:
            conn.execute(
                "UPDATE docs SET relative_path = ?, indexed_at = ? WHERE corpus_id = ? AND relative_path = ?",
                (new_path, time.time(), corpus_id, old_path),
            )

    def delete_doc(self, corpus_id: str, relative_path: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "DELETE FROM docs WHERE corpus_id = ? AND relative_path = ?", (corpus_id, relative_path)
            )

    def doc_count(self, corpus_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM docs WHERE corpus_id = ?", (corpus_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def blob_is_referenced(self, corpus_id: str, blob_sha: str) -> bool:
        """Whether any path in this corpus still points at this content.

        Checked before dropping a blob's vectors: two paths can share one blob, and
        deleting one of them must not blind the other.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM docs WHERE corpus_id = ? AND blob_sha = ? LIMIT 1",
                (corpus_id, blob_sha),
            ).fetchone()
        return row is not None

    def list_docs(self, corpus_id: str, *, limit: int = 0) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM docs WHERE corpus_id = ? ORDER BY relative_path"
        params: List[Any] = [corpus_id]
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def extraction_failures(self, corpus_id: str, *, limit: int = 50) -> List[Dict[str, Any]]:
        """Files that are in the folder but not answerable, and why.

        The honest failure surface. A folder tool that quietly indexes 60% of a folder
        and never says which 40% is missing is worse than one that indexes nothing.
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT d.relative_path, b.extraction_status, b.extraction_error,
                          b.extraction_engine, b.was_scanned
                   FROM docs d JOIN blobs b ON b.blob_sha = d.blob_sha
                   WHERE d.corpus_id = ? AND b.extraction_status != 'extracted'
                   ORDER BY d.relative_path LIMIT ?""",
                (corpus_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------- snapshots

    def save_snapshot(self, corpus_id: str, snapshot: FolderSnapshot) -> None:
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO snapshots(corpus_id, root_sha, payload, taken_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(corpus_id) DO UPDATE SET
                       root_sha=excluded.root_sha,
                       payload=excluded.payload,
                       taken_at=excluded.taken_at""",
                (corpus_id, snapshot.root_sha, json.dumps(_snapshot_as_dict(snapshot)), time.time()),
            )
            conn.execute("DELETE FROM skipped WHERE corpus_id = ?", (corpus_id,))
            conn.executemany(
                "INSERT OR REPLACE INTO skipped(corpus_id, relative_path, reason) VALUES (?, ?, ?)",
                [(corpus_id, path, reason) for path, reason in snapshot.skipped],
            )

    def load_snapshot(self, corpus_id: str) -> Optional[FolderSnapshot]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM snapshots WHERE corpus_id = ?", (corpus_id,)
            ).fetchone()
        if not row:
            return None
        try:
            return _snapshot_from_dict(json.loads(row["payload"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            # A snapshot is a cache, never a source of truth. If it cannot be read the
            # next scan simply re-hashes everything, which is slow but correct.
            return None

    def list_skipped(self, corpus_id: str, *, limit: int = 100) -> List[Dict[str, str]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT relative_path, reason FROM skipped WHERE corpus_id = ? ORDER BY relative_path LIMIT ?",
                (corpus_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


def _corpus_from_row(row: sqlite3.Row) -> CorpusRecord:
    return CorpusRecord(
        corpus_id=row["corpus_id"],
        root_path=row["root_path"],
        label=row["label"],
        root_sha=row["root_sha"],
        embedder_model=row["embedder_model"],
        embedding_dims=int(row["embedding_dims"] or 0),
        status=row["status"],
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        last_error=row["last_error"] or "",
    )


def _line_as_dict(line: ExtractedLine) -> Dict[str, Any]:
    return {"text": line.text, "confidence": line.confidence, "box": list(line.box) if line.box else None}


def _line_from_dict(item: Dict[str, Any]) -> ExtractedLine:
    box = item.get("box")
    return ExtractedLine(
        text=item.get("text", ""),
        confidence=float(item.get("confidence", 1.0)),
        box=tuple(box) if box else None,
    )


def _snapshot_as_dict(snapshot: FolderSnapshot) -> Dict[str, Any]:
    return {
        "root_path": snapshot.root_path,
        "root_sha": snapshot.root_sha,
        "blobs": [
            [entry.relative_path, entry.blob_sha, entry.size_bytes, entry.mtime_ns]
            for entry in snapshot.blobs.values()
        ],
        "trees": [[node.relative_path, node.tree_sha] for node in snapshot.trees.values()],
        "skipped": [list(item) for item in snapshot.skipped],
    }


def _snapshot_from_dict(payload: Dict[str, Any]) -> FolderSnapshot:
    blobs = {
        item[0]: BlobEntry(relative_path=item[0], blob_sha=item[1], size_bytes=item[2], mtime_ns=item[3])
        for item in payload.get("blobs", [])
    }
    trees = {
        item[0]: TreeNode(relative_path=item[0], tree_sha=item[1])
        for item in payload.get("trees", [])
    }
    return FolderSnapshot(
        root_path=payload.get("root_path", ""),
        root_sha=payload.get("root_sha", ""),
        blobs=blobs,
        trees=trees,
        skipped=tuple((item[0], item[1]) for item in payload.get("skipped", [])),
    )
