"""Keeping a folder's index in step with the folder, as cheaply as possible.

The whole design answers one question: when the user drops a file into a folder they
pointed at an hour ago, what is the minimum work needed before they can ask about it?

`sync()` is that answer, and it is deliberately boring:

    scan (stat cache) -> diff (Merkle) -> extract (blob cache) -> chunk -> embed (chunk cache)

Every arrow has a cache behind it, and each cache is keyed by content rather than by
path. The effect compounds: an unchanged file is never read, a moved file is never
extracted, a duplicated file is never embedded, and a re-run over a settled folder does
no network work at all. That last property is what makes a filesystem watcher safe to
attach — a spurious event costs a stat pass, not an embedding bill.

Progress is reported through a callback rather than a return value, because the useful
version of this feature answers questions *while* the first index is still running.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from dhee.corpus.extract import (
    Chunk,
    ExtractedDoc,
    ExtractorChain,
    PlainTextExtractor,
    TextExtractor,
    chunk_document,
)
from dhee.corpus.store import CorpusStore
from dhee.corpus.tree import BlobEntry, FolderDiff, FolderSnapshot, diff, scan

logger = logging.getLogger(__name__)

STATUS_NEW = "new"
STATUS_INDEXING = "indexing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

DEFAULT_EMBED_BATCH = 128


@dataclass
class SyncProgress:
    """What the UI needs to say something honest while work is in flight."""

    corpus_id: str
    phase: str = "scanning"
    files_total: int = 0
    files_done: int = 0
    chunks_embedded: int = 0
    chunks_reused: int = 0
    current_path: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "phase": self.phase,
            "files_total": self.files_total,
            "files_done": self.files_done,
            "chunks_embedded": self.chunks_embedded,
            "chunks_reused": self.chunks_reused,
            "current_path": self.current_path,
        }


@dataclass
class SyncReport:
    """What the sync actually cost, in the units that matter."""

    corpus_id: str
    root_sha: str = ""
    changed: Dict[str, int] = field(default_factory=dict)
    files_extracted: int = 0
    extraction_reused: int = 0
    chunks_embedded: int = 0
    chunks_reused: int = 0
    failures: List[Dict[str, str]] = field(default_factory=list)
    duration_seconds: float = 0.0
    unchanged: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "root_sha": self.root_sha,
            "changed": self.changed,
            "files_extracted": self.files_extracted,
            "extraction_reused": self.extraction_reused,
            "chunks_embedded": self.chunks_embedded,
            "chunks_reused": self.chunks_reused,
            "failures": self.failures,
            "duration_seconds": round(self.duration_seconds, 3),
            "unchanged": self.unchanged,
        }


class CorpusIndex:
    """One folder, indexed and kept in step.

    The vector store is injected rather than constructed here so a caller can hand in
    an in-memory store for tests and a sqlite-vec one in production, and so the corpus
    never reaches into Dhee's belief-memory configuration by accident.
    """

    def __init__(
        self,
        *,
        store: CorpusStore,
        vector_store: Any,
        embedder: Any,
        extractor: Optional[TextExtractor] = None,
        embed_batch_size: int = DEFAULT_EMBED_BATCH,
    ):
        self.store = store
        self.vector_store = vector_store
        self.embedder = embedder
        self.extractor = extractor or ExtractorChain([PlainTextExtractor()])
        self.embed_batch_size = max(1, embed_batch_size)
        self.model_name = str(getattr(embedder, "model", None) or embedder.__class__.__name__)

    # ----------------------------------------------------------------- attach

    def attach(self, root: Path | str, *, label: str = "") -> str:
        """Bind a folder to a corpus id, reusing the existing one if already bound.

        Idempotent on purpose: the user picking the same folder twice must not create a
        second index and a second embedding bill.
        """
        root_path = str(Path(root).expanduser().resolve())
        existing = self.store.get_corpus_by_root(root_path)
        corpus_id = existing.corpus_id if existing else uuid.uuid4().hex[:16]
        self.store.upsert_corpus(
            corpus_id=corpus_id,
            root_path=root_path,
            label=label or Path(root_path).name,
            embedder_model=self.model_name,
            embedding_dims=int(getattr(self.embedder, "dims", 0) or 0),
        )
        return corpus_id

    # ------------------------------------------------------------------- sync

    def sync(
        self,
        corpus_id: str,
        *,
        include: Optional[Callable[[Path], bool]] = None,
        on_progress: Optional[Callable[[SyncProgress], None]] = None,
        force: bool = False,
    ) -> SyncReport:
        started = time.monotonic()
        record = self.store.get_corpus(corpus_id)
        if record is None:
            raise KeyError(f"unknown corpus: {corpus_id}")

        progress = SyncProgress(corpus_id=corpus_id)
        report = SyncReport(corpus_id=corpus_id)

        def emit(phase: str, **updates: Any) -> None:
            progress.phase = phase
            for key, value in updates.items():
                setattr(progress, key, value)
            if on_progress is not None:
                on_progress(progress)

        emit("scanning")
        previous = None if force else self.store.load_snapshot(corpus_id)
        predicate = include or self._default_include
        try:
            snapshot = scan(record.root_path, include=predicate, previous=previous)
        except (OSError, NotADirectoryError) as exc:
            self.store.set_corpus_state(corpus_id, status=STATUS_FAILED, last_error=str(exc))
            report.failures.append({"relative_path": "", "reason": str(exc)})
            report.duration_seconds = time.monotonic() - started
            return report

        report.root_sha = snapshot.root_sha

        # The cheapest possible outcome, and the common one for a watcher-triggered
        # run: one root hash comparison and we are done.
        if previous is not None and previous.root_sha == snapshot.root_sha and not force:
            self.store.set_corpus_state(corpus_id, status=STATUS_READY, root_sha=snapshot.root_sha)
            report.unchanged = True
            report.changed = FolderDiff().as_dict()
            report.duration_seconds = time.monotonic() - started
            emit("ready")
            return report

        changes = diff(previous, snapshot)
        report.changed = changes.as_dict()
        self.store.set_corpus_state(corpus_id, status=STATUS_INDEXING, last_error="")

        # Renames first: they are pure bookkeeping, and doing them before deletes stops
        # a moved file from being torn down and rebuilt.
        for renamed in changes.renamed:
            self.store.move_doc(corpus_id, renamed.old_path, renamed.new_path)

        for removed in changes.deleted:
            self._forget(corpus_id, removed)

        pending = changes.needs_extraction
        emit("indexing", files_total=len(pending), files_done=0)

        for position, entry in enumerate(pending, start=1):
            emit("indexing", files_done=position - 1, current_path=entry.relative_path)
            try:
                self._index_file(corpus_id, Path(record.root_path) / entry.relative_path, entry, report, progress)
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the folder
                logger.warning("corpus %s: failed on %s: %s", corpus_id, entry.relative_path, exc)
                report.failures.append({"relative_path": entry.relative_path, "reason": str(exc)})
            self.store.put_doc(corpus_id, entry)

        emit("indexing", files_done=len(pending), current_path="")

        self.store.save_snapshot(corpus_id, snapshot)
        self.store.set_corpus_state(corpus_id, status=STATUS_READY, root_sha=snapshot.root_sha)
        report.duration_seconds = time.monotonic() - started
        emit("ready")
        return report

    # -------------------------------------------------------------- internals

    def _index_file(
        self,
        corpus_id: str,
        path: Path,
        entry: BlobEntry,
        report: SyncReport,
        progress: SyncProgress,
    ) -> None:
        blob_sha = entry.blob_sha

        if self.store.blob_is_extracted(blob_sha):
            # Seen this exact content before — possibly under another name, possibly in
            # another folder entirely. Reuse everything.
            report.extraction_reused += 1
            chunks = self.store.chunks_for_blob(blob_sha)
        else:
            doc = self._extract(path)
            self.store.save_extraction(blob_sha=blob_sha, size_bytes=entry.size_bytes, doc=doc)
            report.files_extracted += 1
            if not doc.is_usable:
                report.failures.append(
                    {
                        "relative_path": entry.relative_path,
                        "reason": doc.error or doc.status,
                    }
                )
                return
            chunks = chunk_document(blob_sha=blob_sha, doc=doc)
            self.store.save_chunks(chunks)

        if chunks:
            self._embed_chunks(corpus_id, chunks, report, progress)

    def _extract(self, path: Path) -> ExtractedDoc:
        if not self.extractor.supports(path):
            return ExtractedDoc.failure(
                f"no extractor handles {path.suffix or 'this file type'}", status="unsupported"
            )
        return self.extractor.extract(path)

    def _embed_chunks(
        self,
        corpus_id: str,
        chunks: Sequence[Chunk],
        report: SyncReport,
        progress: SyncProgress,
    ) -> None:
        by_id = {chunk.chunk_id: chunk for chunk in chunks}
        todo = self.store.unembedded_chunk_ids(corpus_id, list(by_id), self.model_name)
        reused = len(by_id) - len(todo)
        report.chunks_reused += reused
        progress.chunks_reused = report.chunks_reused
        if not todo:
            return

        for start in range(0, len(todo), self.embed_batch_size):
            window = todo[start : start + self.embed_batch_size]
            batch = [by_id[chunk_id] for chunk_id in window]
            vectors = self.embedder.embed_batch([chunk.text for chunk in batch])
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"embedder returned {len(vectors)} vectors for {len(batch)} chunks"
                )
            self.vector_store.insert(
                vectors=vectors,
                payloads=[self._payload(corpus_id, chunk) for chunk in batch],
                ids=[chunk.chunk_id for chunk in batch],
            )
            self.store.mark_embedded(corpus_id, window, self.model_name)
            report.chunks_embedded += len(batch)
            progress.chunks_embedded = report.chunks_embedded

    @staticmethod
    def _payload(corpus_id: str, chunk: Chunk) -> Dict[str, Any]:
        # Kept deliberately thin. The payload is a pointer, not a copy: the text and the
        # citation are rehydrated from sqlite at search time, so a file that moves or is
        # deleted cannot leave a stale path baked into the vector store.
        return {
            "corpus_id": corpus_id,
            "chunk_id": chunk.chunk_id,
            "blob_sha": chunk.blob_sha,
            "page_no": chunk.page_no,
        }

    def _forget(self, corpus_id: str, entry: BlobEntry) -> None:
        """Drop a deleted file, keeping content another path still needs."""
        self.store.delete_doc(corpus_id, entry.relative_path)
        if self.store.blob_is_referenced(corpus_id, entry.blob_sha):
            return
        chunk_ids = [chunk.chunk_id for chunk in self.store.chunks_for_blob(entry.blob_sha)]
        for chunk_id in chunk_ids:
            try:
                self.vector_store.delete(chunk_id)
            except Exception:  # noqa: BLE001 - a missing vector is already the goal
                pass
        self.store.forget_embeddings(corpus_id, chunk_ids, self.model_name)

    def _default_include(self, path: Path) -> bool:
        return self.extractor.supports(path)

    # ------------------------------------------------------------------ status

    def status(self, corpus_id: str) -> Dict[str, Any]:
        record = self.store.get_corpus(corpus_id)
        if record is None:
            return {"corpus_id": corpus_id, "status": "unknown"}
        payload = record.as_dict()
        payload.update(
            {
                "file_count": self.store.doc_count(corpus_id),
                "failures": self.store.extraction_failures(corpus_id, limit=20),
                "skipped": self.store.list_skipped(corpus_id, limit=20),
            }
        )
        return payload
