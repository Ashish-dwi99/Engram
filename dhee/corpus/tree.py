"""Folder change tracking, shaped like git's object model.

A corpus is expensive to build: every new chunk costs an OCR pass and a metered
embedding call. So the question this module answers is not "what is in the folder"
but "what is *different* since last time", and it answers it without reading files
it does not have to.

Three ideas, all borrowed from git because git already solved this:

1. **Content addressing.** A file is identified by the sha256 of its bytes, never by
   its path. Two copies of the same PDF in different folders are one blob. A file
   that moves keeps its identity. Everything downstream — extracted text, chunks,
   embeddings — is cached against the blob hash, so a moved or duplicated file costs
   nothing to re-index.

2. **Merkle directory nodes.** A directory's hash is derived from its sorted children,
   so a single root hash answers "did anything at all change?" in one comparison, and
   a subtree whose hash is unchanged provably contains no changes anywhere beneath it.

3. **A stat cache.** Hashing bytes is the expensive part of a scan. Git avoids it by
   trusting `(size, mtime_ns)` from the previous index, and so do we: a file whose size
   and mtime both match the last snapshot is not re-read. This is what makes a re-scan
   of a large folder cost close to nothing when little has changed.

Rename detection then falls out for free rather than needing a heuristic: a path that
disappeared and a path that appeared carrying the *same* blob hash is one file that
moved, and moving a file must never re-OCR or re-embed it.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, Iterator, Mapping, Optional, Tuple

# Directories that are never part of a document corpus. Walking them is not just
# wasted work: node_modules and .git can each hold more files than the corpus itself,
# which would make every scan look like a large diff.
PRUNED_DIR_NAMES = frozenset({
    ".git",
    ".hg",
    ".svn",
    ".dhee",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".next",
    ".turbo",
    "dist",
    "build",
    "target",
    ".Trash",
    ".DS_Store",
})

_READ_CHUNK_BYTES = 1024 * 1024

# The hash of an empty directory listing. Kept as a constant so an empty folder and a
# folder whose children were all pruned hash identically and compare as unchanged.
EMPTY_TREE_SHA = hashlib.sha256(b"tree\0").hexdigest()


@dataclass(frozen=True, slots=True)
class BlobEntry:
    """One file, identified by content rather than by where it happens to sit."""

    relative_path: str
    blob_sha: str
    size_bytes: int
    mtime_ns: int

    @property
    def name(self) -> str:
        return self.relative_path.rsplit("/", 1)[-1]

    @property
    def suffix(self) -> str:
        return Path(self.relative_path).suffix.lower()

    def stat_matches(self, size_bytes: int, mtime_ns: int) -> bool:
        """True when the stat cache may be trusted to skip re-hashing this file.

        Both fields must agree. Size alone misses in-place edits that preserve length;
        mtime alone misses filesystems and restore tools that preserve timestamps.
        """
        return self.size_bytes == size_bytes and self.mtime_ns == mtime_ns


@dataclass(frozen=True, slots=True)
class TreeNode:
    """A directory, hashed from its sorted children.

    ``entries`` holds ``(name, kind, sha)`` triples where kind is ``blob`` or ``tree``.
    """

    relative_path: str
    tree_sha: str
    entries: Tuple[Tuple[str, str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FolderSnapshot:
    """The state of a folder at one moment, addressable by its root hash."""

    root_path: str
    root_sha: str
    blobs: Mapping[str, BlobEntry] = field(default_factory=dict)
    trees: Mapping[str, TreeNode] = field(default_factory=dict)
    skipped: Tuple[Tuple[str, str], ...] = ()

    @property
    def file_count(self) -> int:
        return len(self.blobs)

    def blob_paths_by_sha(self) -> Dict[str, Tuple[str, ...]]:
        """Group paths by content, so duplicates and moves are visible at a glance."""
        grouped: Dict[str, list] = {}
        for entry in self.blobs.values():
            grouped.setdefault(entry.blob_sha, []).append(entry.relative_path)
        return {sha: tuple(sorted(paths)) for sha, paths in grouped.items()}


@dataclass(frozen=True, slots=True)
class RenamedBlob:
    old_path: str
    new_path: str
    blob_sha: str


@dataclass(frozen=True, slots=True)
class FolderDiff:
    """What changed between two snapshots, in the units the indexer bills in.

    ``added`` and ``modified`` are the only two that cost extraction and embedding.
    ``renamed`` costs a metadata update. ``deleted`` costs a delete. Everything else
    was not even read off disk.
    """

    added: Tuple[BlobEntry, ...] = ()
    modified: Tuple[BlobEntry, ...] = ()
    deleted: Tuple[BlobEntry, ...] = ()
    renamed: Tuple[RenamedBlob, ...] = ()
    unchanged_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.modified or self.deleted or self.renamed)

    @property
    def needs_extraction(self) -> Tuple[BlobEntry, ...]:
        """Files whose content the indexer has not seen before at this hash."""
        return self.added + self.modified

    def as_dict(self) -> Dict[str, int]:
        return {
            "added": len(self.added),
            "modified": len(self.modified),
            "deleted": len(self.deleted),
            "renamed": len(self.renamed),
            "unchanged": self.unchanged_count,
        }


def hash_file(path: Path) -> str:
    """sha256 of the file's bytes, streamed so a large PDF never lands in memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(_READ_CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def hash_tree(entries: Iterable[Tuple[str, str, str]]) -> str:
    """Hash a directory from its children.

    Sorted by name so the hash depends on content and structure only, never on the
    order the filesystem happened to hand entries back. The length prefix on each
    field keeps the encoding unambiguous, so a file cleverly named to look like two
    entries cannot collide with a real pair.
    """
    digest = hashlib.sha256()
    digest.update(b"tree\0")
    for name, kind, sha in sorted(entries):
        record = f"{kind}:{len(name)}:{name}:{sha}".encode("utf-8")
        digest.update(len(record).to_bytes(4, "big"))
        digest.update(record)
    return digest.hexdigest()


def scan(
    root: Path | str,
    *,
    include: Optional[Callable[[Path], bool]] = None,
    previous: Optional[FolderSnapshot] = None,
    pruned_dirs: frozenset = PRUNED_DIR_NAMES,
    follow_symlinks: bool = False,
) -> FolderSnapshot:
    """Walk ``root`` and build a snapshot, re-hashing only what the stat cache misses.

    ``previous`` is the snapshot from the last scan. When a file's size and mtime both
    match what that snapshot recorded, its hash is carried over and the bytes are never
    read — which is what keeps a re-scan of a settled folder nearly free.

    ``include`` decides which files belong to the corpus at all. Rejected files are
    recorded in ``skipped`` with a reason rather than silently dropped, because "why is
    my document not searchable" needs an answer.
    """
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise NotADirectoryError(f"corpus root is not a directory: {root_path}")

    prior_blobs: Mapping[str, BlobEntry] = previous.blobs if previous else {}
    blobs: Dict[str, BlobEntry] = {}
    trees: Dict[str, TreeNode] = {}
    skipped: list[Tuple[str, str]] = []

    def relative(path: Path) -> str:
        return path.relative_to(root_path).as_posix()

    def walk(directory: Path) -> str:
        """Depth-first, returning this directory's tree hash."""
        entries: list[Tuple[str, str, str]] = []
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name)
        except PermissionError:
            skipped.append((relative(directory) if directory != root_path else "", "permission_denied"))
            children = []

        for child in children:
            name = child.name
            if name in pruned_dirs or name.startswith("._"):
                continue
            try:
                is_dir = child.is_dir(follow_symlinks=follow_symlinks)
            except OSError:
                continue

            child_path = Path(child.path)
            if is_dir:
                entries.append((name, "tree", walk(child_path)))
                continue

            if not follow_symlinks and child.is_symlink():
                # A symlink can point outside the root; the corpus stays inside it.
                skipped.append((relative(child_path), "symlink"))
                continue

            rel = relative(child_path)
            if include is not None and not include(child_path):
                skipped.append((rel, "unsupported_file_type"))
                continue

            try:
                stat = child.stat(follow_symlinks=follow_symlinks)
            except OSError:
                skipped.append((rel, "stat_failed"))
                continue

            cached = prior_blobs.get(rel)
            if cached is not None and cached.stat_matches(stat.st_size, stat.st_mtime_ns):
                blob_sha = cached.blob_sha
            else:
                try:
                    blob_sha = hash_file(child_path)
                except OSError:
                    skipped.append((rel, "read_failed"))
                    continue

            blobs[rel] = BlobEntry(
                relative_path=rel,
                blob_sha=blob_sha,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
            entries.append((name, "blob", blob_sha))

        tree_sha = hash_tree(entries) if entries else EMPTY_TREE_SHA
        rel_dir = "" if directory == root_path else relative(directory)
        trees[rel_dir] = TreeNode(relative_path=rel_dir, tree_sha=tree_sha, entries=tuple(entries))
        return tree_sha

    root_sha = walk(root_path)
    return FolderSnapshot(
        root_path=str(root_path),
        root_sha=root_sha,
        blobs=blobs,
        trees=trees,
        skipped=tuple(sorted(skipped)),
    )


def changed_subtrees(old: Optional[FolderSnapshot], new: FolderSnapshot) -> Tuple[str, ...]:
    """Directories whose hash differs, i.e. the only places a change can be.

    Not needed to compute a diff — ``scan`` already holds every path — but it is what
    makes "did anything change under this folder?" answerable without a diff at all,
    and it is the signal a watcher uses to decide whether to bother.
    """
    if old is None:
        return tuple(sorted(new.trees))
    return tuple(sorted(
        path for path, node in new.trees.items()
        if (old.trees.get(path).tree_sha if old.trees.get(path) else None) != node.tree_sha
    ))


def diff(old: Optional[FolderSnapshot], new: FolderSnapshot) -> FolderDiff:
    """Classify what changed, resolving moves before reporting adds and deletes.

    Order matters here. A file that moved looks exactly like one delete plus one add
    until you notice both carry the same blob hash — and reporting it as an add would
    charge a full OCR and embedding pass for a file whose content is already indexed.
    """
    if old is None:
        return FolderDiff(added=tuple(new.blobs[path] for path in sorted(new.blobs)))

    old_paths = set(old.blobs)
    new_paths = set(new.blobs)

    added_paths = new_paths - old_paths
    deleted_paths = old_paths - new_paths

    modified: list[BlobEntry] = []
    unchanged = 0
    for path in sorted(old_paths & new_paths):
        if old.blobs[path].blob_sha != new.blobs[path].blob_sha:
            modified.append(new.blobs[path])
        else:
            unchanged += 1

    # Pair up disappearances and appearances that share content. Both sides are
    # consumed in sorted order so a file duplicated into two new paths resolves
    # deterministically rather than depending on set iteration order.
    deleted_by_sha: Dict[str, list] = {}
    for path in sorted(deleted_paths):
        deleted_by_sha.setdefault(old.blobs[path].blob_sha, []).append(path)

    renamed: list[RenamedBlob] = []
    still_added: list[BlobEntry] = []
    for path in sorted(added_paths):
        entry = new.blobs[path]
        candidates = deleted_by_sha.get(entry.blob_sha)
        if candidates:
            renamed.append(RenamedBlob(old_path=candidates.pop(0), new_path=path, blob_sha=entry.blob_sha))
            if not candidates:
                deleted_by_sha.pop(entry.blob_sha, None)
        else:
            still_added.append(entry)

    still_deleted = [
        old.blobs[path]
        for sha_paths in deleted_by_sha.values()
        for path in sha_paths
    ]

    return FolderDiff(
        added=tuple(still_added),
        modified=tuple(modified),
        deleted=tuple(sorted(still_deleted, key=lambda item: item.relative_path)),
        renamed=tuple(renamed),
        unchanged_count=unchanged,
    )


def iter_blobs(snapshot: FolderSnapshot) -> Iterator[BlobEntry]:
    for path in sorted(snapshot.blobs):
        yield snapshot.blobs[path]
