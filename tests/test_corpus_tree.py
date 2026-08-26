"""The corpus tree's job is to not spend money. These tests assert that.

Every case here is really one question: after this change to the folder, how many
files does the indexer have to extract and embed? The answer must be "only the ones
whose content the indexer has never seen", and in particular it must be zero for a
rename, a move, and a no-op re-scan.
"""

from __future__ import annotations

import os
import shutil

import pytest

from dhee.corpus.tree import (
    EMPTY_TREE_SHA,
    FolderDiff,
    changed_subtrees,
    diff,
    hash_tree,
    scan,
)


@pytest.fixture()
def folder(tmp_path):
    (tmp_path / "orders").mkdir()
    (tmp_path / "notes").mkdir()
    (tmp_path / "orders" / "order-1.txt").write_text("penalty is 2% per week", encoding="utf-8")
    (tmp_path / "orders" / "order-2.txt").write_text("payment terms are net 30", encoding="utf-8")
    (tmp_path / "notes" / "meeting.md").write_text("agreed the pricing schedule", encoding="utf-8")
    return tmp_path


def test_scan_hashes_by_content_and_finds_every_file(folder):
    snapshot = scan(folder)

    assert snapshot.file_count == 3
    assert set(snapshot.blobs) == {"orders/order-1.txt", "orders/order-2.txt", "notes/meeting.md"}
    assert snapshot.root_sha != EMPTY_TREE_SHA
    # Directory nodes exist for the root and each subdirectory.
    assert set(snapshot.trees) == {"", "orders", "notes"}


def test_rescan_of_untouched_folder_is_a_no_op(folder):
    first = scan(folder)
    second = scan(folder, previous=first)

    assert second.root_sha == first.root_sha
    result = diff(first, second)
    assert result.is_empty
    assert result.needs_extraction == ()
    assert result.unchanged_count == 3


def test_rename_costs_nothing_to_reindex(folder):
    first = scan(folder)
    os.rename(folder / "orders" / "order-1.txt", folder / "orders" / "renamed-order.txt")
    second = scan(folder, previous=first)

    result = diff(first, second)
    assert len(result.renamed) == 1
    assert result.renamed[0].old_path == "orders/order-1.txt"
    assert result.renamed[0].new_path == "orders/renamed-order.txt"
    # The whole point: a rename is not an add and not a delete, so nothing is re-read.
    assert result.added == ()
    assert result.deleted == ()
    assert result.needs_extraction == ()


def test_move_across_directories_is_also_a_rename(folder):
    first = scan(folder)
    shutil.move(str(folder / "orders" / "order-2.txt"), str(folder / "notes" / "order-2.txt"))
    second = scan(folder, previous=first)

    result = diff(first, second)
    assert [(item.old_path, item.new_path) for item in result.renamed] == [
        ("orders/order-2.txt", "notes/order-2.txt")
    ]
    assert result.needs_extraction == ()


def test_duplicate_file_shares_one_blob(folder):
    shutil.copy(folder / "orders" / "order-1.txt", folder / "notes" / "copy-of-order-1.txt")
    snapshot = scan(folder)

    by_sha = snapshot.blob_paths_by_sha()
    duplicated = [paths for paths in by_sha.values() if len(paths) > 1]
    assert duplicated == [("notes/copy-of-order-1.txt", "orders/order-1.txt")]
    # Four paths, but only three distinct pieces of content to ever embed.
    assert snapshot.file_count == 4
    assert len(by_sha) == 3


def test_edit_is_a_modification_not_an_add(folder):
    first = scan(folder)
    (folder / "orders" / "order-1.txt").write_text("penalty is now 5% per week", encoding="utf-8")
    second = scan(folder, previous=first)

    result = diff(first, second)
    assert [item.relative_path for item in result.modified] == ["orders/order-1.txt"]
    assert result.added == ()
    assert result.renamed == ()
    assert len(result.needs_extraction) == 1


def test_in_place_edit_preserving_size_is_still_detected(folder):
    """The stat cache must not be trusted past what it can actually prove.

    An edit that keeps the byte count identical is exactly the case where a size-only
    check would wave the file through as unchanged.
    """
    first = scan(folder)
    original = (folder / "orders" / "order-1.txt").read_text(encoding="utf-8")
    replacement = "PENALTY IS 2% PER WEEK"
    assert len(replacement) == len(original)
    (folder / "orders" / "order-1.txt").write_text(replacement, encoding="utf-8")

    second = scan(folder, previous=first)
    result = diff(first, second)
    assert [item.relative_path for item in result.modified] == ["orders/order-1.txt"]


def test_delete_and_add_are_reported_separately(folder):
    first = scan(folder)
    (folder / "notes" / "meeting.md").unlink()
    (folder / "orders" / "order-3.txt").write_text("indemnity clause", encoding="utf-8")
    second = scan(folder, previous=first)

    result = diff(first, second)
    assert [item.relative_path for item in result.deleted] == ["notes/meeting.md"]
    assert [item.relative_path for item in result.added] == ["orders/order-3.txt"]
    assert result.renamed == ()


def test_first_scan_reports_everything_as_added(folder):
    snapshot = scan(folder)
    result = diff(None, snapshot)

    assert len(result.added) == 3
    assert result.unchanged_count == 0
    assert len(result.needs_extraction) == 3


def test_root_hash_changes_only_when_content_changes(folder):
    first = scan(folder)
    # Touching mtime without changing bytes must not move the root hash: content
    # addressing is the whole promise.
    os.utime(folder / "orders" / "order-1.txt", None)
    second = scan(folder)
    assert second.root_sha == first.root_sha

    (folder / "orders" / "order-1.txt").write_text("different", encoding="utf-8")
    third = scan(folder)
    assert third.root_sha != first.root_sha


def test_changed_subtrees_localises_the_change(folder):
    first = scan(folder)
    (folder / "notes" / "meeting.md").write_text("agreed a different schedule", encoding="utf-8")
    second = scan(folder, previous=first)

    changed = changed_subtrees(first, second)
    # The edited directory and the root that contains it; `orders` is provably clean.
    assert set(changed) == {"", "notes"}


def test_include_predicate_records_why_a_file_was_skipped(folder):
    (folder / "orders" / "scan.tiff").write_bytes(b"not indexable here")
    snapshot = scan(folder, include=lambda path: path.suffix.lower() in {".txt", ".md"})

    assert "orders/scan.tiff" not in snapshot.blobs
    assert ("orders/scan.tiff", "unsupported_file_type") in snapshot.skipped


def test_pruned_directories_are_never_walked(folder):
    noisy = folder / "node_modules" / "pkg"
    noisy.mkdir(parents=True)
    (noisy / "index.js").write_text("module.exports = {}", encoding="utf-8")

    snapshot = scan(folder)
    assert not any(path.startswith("node_modules") for path in snapshot.blobs)
    assert "node_modules" not in snapshot.trees


def test_symlinks_are_skipped_so_the_corpus_stays_inside_the_root(folder, tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("should not be indexed", encoding="utf-8")
    try:
        os.symlink(outside, folder / "notes" / "link.txt")
    except OSError:
        pytest.skip("symlinks not permitted in this environment")

    snapshot = scan(folder)
    assert "notes/link.txt" not in snapshot.blobs
    assert ("notes/link.txt", "symlink") in snapshot.skipped


def test_empty_directory_hashes_to_the_empty_tree(tmp_path):
    (tmp_path / "empty").mkdir()
    snapshot = scan(tmp_path)
    assert snapshot.trees["empty"].tree_sha == EMPTY_TREE_SHA


def test_tree_hash_is_order_independent_but_name_sensitive():
    a = hash_tree([("b.txt", "blob", "sha-2"), ("a.txt", "blob", "sha-1")])
    b = hash_tree([("a.txt", "blob", "sha-1"), ("b.txt", "blob", "sha-2")])
    assert a == b

    renamed = hash_tree([("a.txt", "blob", "sha-1"), ("c.txt", "blob", "sha-2")])
    assert renamed != a


def test_tree_hash_encoding_is_unambiguous():
    """Names must not be able to run together into a colliding encoding."""
    first = hash_tree([("a:b", "blob", "sha-1")])
    second = hash_tree([("a", "blob", "b:sha-1")])
    assert first != second


def test_diff_summary_is_reportable(folder):
    first = scan(folder)
    (folder / "orders" / "order-4.txt").write_text("new", encoding="utf-8")
    second = scan(folder, previous=first)

    assert diff(first, second).as_dict() == {
        "added": 1,
        "modified": 0,
        "deleted": 0,
        "renamed": 0,
        "unchanged": 3,
    }


def test_empty_diff_is_falsy_on_a_fresh_folder(tmp_path):
    snapshot = scan(tmp_path)
    assert diff(snapshot, snapshot) == FolderDiff(unchanged_count=0)
