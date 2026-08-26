"""The indexer's contract is about what it *doesn't* do.

Extraction is slow and embedding is a metered network call, so both are counted here by
fake collaborators. Assertions are on call counts as much as on results: a rename that
re-embeds is a correctness bug in the only dimension that matters at scale.
"""

from __future__ import annotations

import os
import shutil

import pytest

from dhee.corpus.extract import ExtractedDoc, ExtractedPage
from dhee.corpus.index import CorpusIndex, STATUS_READY
from dhee.corpus.search import CorpusSearch
from dhee.corpus.store import CorpusStore


class CountingExtractor:
    """A text reader that remembers how often it was asked to work."""

    def __init__(self):
        self.calls: list[str] = []

    def supports(self, path) -> bool:
        return path.suffix.lower() in {".txt", ".md"}

    def extract(self, path) -> ExtractedDoc:
        self.calls.append(path.name)
        body = path.read_text(encoding="utf-8")
        pages = [
            ExtractedPage(page_no=number, text=block.strip())
            for number, block in enumerate(body.split("\f"), start=1)
            if block.strip()
        ]
        if not pages:
            return ExtractedDoc(status="empty", error="no text", engine="counting")
        return ExtractedDoc(pages=tuple(pages), engine="counting")


class CountingEmbedder:
    """Deterministic bag-of-words vectors, and a tally of what was embedded."""

    model = "test-embedder"
    dims = 16

    def __init__(self):
        self.embedded: list[str] = []

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dims
        for token in text.lower().split():
            vector[hash(token) % self.dims] += 1.0
        norm = sum(value * value for value in vector) ** 0.5
        return [value / norm for value in vector] if norm else vector

    def embed(self, text: str, memory_action=None) -> list[float]:
        return self._vector(text)

    def embed_batch(self, texts, memory_action=None) -> list[list[float]]:
        self.embedded.extend(texts)
        return [self._vector(text) for text in texts]


class FakeVectorStore:
    """Enough of the vector-store surface to exercise insert / search / delete."""

    def __init__(self):
        self.vectors: dict[str, list[float]] = {}
        self.payloads: dict[str, dict] = {}

    def insert(self, vectors, payloads=None, ids=None):
        payloads = payloads or [{} for _ in vectors]
        for vector, payload, key in zip(vectors, payloads, ids):
            self.vectors[key] = vector
            self.payloads[key] = payload

    def search(self, query, vectors, limit=5, filters=None):
        def cosine(other):
            return sum(a * b for a, b in zip(vectors, other))

        ranked = sorted(self.vectors.items(), key=lambda item: cosine(item[1]), reverse=True)
        return [{"id": key, "score": cosine(vector)} for key, vector in ranked[:limit]]

    def delete(self, vector_id):
        self.vectors.pop(vector_id, None)
        self.payloads.pop(vector_id, None)


@pytest.fixture()
def rig(tmp_path):
    root = tmp_path / "folder"
    root.mkdir()
    (root / "penalty.txt").write_text(
        "The penalty for late delivery is two percent per week of the undelivered value. "
        "This is capped at ten percent of the total contract price.",
        encoding="utf-8",
    )
    (root / "office.txt").write_text(
        "The registered office of the company is located in Mumbai, Maharashtra, "
        "and all notices must be served at that address.",
        encoding="utf-8",
    )

    extractor = CountingExtractor()
    embedder = CountingEmbedder()
    vectors = FakeVectorStore()
    store = CorpusStore(tmp_path / "corpus.db")
    index = CorpusIndex(store=store, vector_store=vectors, embedder=embedder, extractor=extractor)
    corpus_id = index.attach(root)
    yield {
        "root": root,
        "store": store,
        "index": index,
        "search": CorpusSearch(store=store, vector_store=vectors, embedder=embedder),
        "extractor": extractor,
        "embedder": embedder,
        "vectors": vectors,
        "corpus_id": corpus_id,
    }
    store.close()


def test_first_sync_indexes_everything(rig):
    report = rig["index"].sync(rig["corpus_id"])

    assert report.changed["added"] == 2
    assert report.files_extracted == 2
    assert report.chunks_embedded > 0
    assert rig["store"].doc_count(rig["corpus_id"]) == 2
    assert rig["index"].status(rig["corpus_id"])["status"] == STATUS_READY


def test_second_sync_does_no_work_at_all(rig):
    rig["index"].sync(rig["corpus_id"])
    rig["extractor"].calls.clear()
    rig["embedder"].embedded.clear()

    report = rig["index"].sync(rig["corpus_id"])

    assert report.unchanged is True
    assert rig["extractor"].calls == []
    assert rig["embedder"].embedded == []


def test_rename_costs_no_extraction_and_no_embedding(rig):
    rig["index"].sync(rig["corpus_id"])
    rig["extractor"].calls.clear()
    rig["embedder"].embedded.clear()

    os.rename(rig["root"] / "penalty.txt", rig["root"] / "penalty-clause.txt")
    report = rig["index"].sync(rig["corpus_id"])

    assert report.changed["renamed"] == 1
    assert report.changed["added"] == 0
    assert rig["extractor"].calls == []
    assert rig["embedder"].embedded == []
    # And the file is still answerable under its new name.
    paths = {doc["relative_path"] for doc in rig["store"].list_docs(rig["corpus_id"])}
    assert paths == {"penalty-clause.txt", "office.txt"}


def test_duplicate_file_is_extracted_and_embedded_once(rig):
    rig["index"].sync(rig["corpus_id"])
    rig["extractor"].calls.clear()
    rig["embedder"].embedded.clear()

    shutil.copy(rig["root"] / "penalty.txt", rig["root"] / "penalty-copy.txt")
    report = rig["index"].sync(rig["corpus_id"])

    assert report.changed["added"] == 1
    # Content already seen: no extraction, no embedding, just a new path.
    assert rig["extractor"].calls == []
    assert rig["embedder"].embedded == []
    assert report.extraction_reused == 1
    assert rig["store"].doc_count(rig["corpus_id"]) == 3


def test_new_file_only_embeds_the_new_file(rig):
    rig["index"].sync(rig["corpus_id"])
    rig["extractor"].calls.clear()
    rig["embedder"].embedded.clear()

    (rig["root"] / "indemnity.txt").write_text(
        "The supplier shall indemnify the buyer against all third party claims "
        "arising from defective goods supplied under this agreement.",
        encoding="utf-8",
    )
    report = rig["index"].sync(rig["corpus_id"])

    assert rig["extractor"].calls == ["indemnity.txt"]
    assert report.files_extracted == 1
    assert all("indemnify" in text or "supplier" in text for text in rig["embedder"].embedded)


def test_edited_file_is_re_embedded(rig):
    rig["index"].sync(rig["corpus_id"])
    rig["extractor"].calls.clear()
    rig["embedder"].embedded.clear()

    (rig["root"] / "penalty.txt").write_text(
        "The penalty for late delivery is now five percent per week of the undelivered value, "
        "capped at twenty percent of the contract price.",
        encoding="utf-8",
    )
    report = rig["index"].sync(rig["corpus_id"])

    assert report.changed["modified"] == 1
    assert rig["extractor"].calls == ["penalty.txt"]
    assert any("five percent" in text for text in rig["embedder"].embedded)


def test_deleted_file_stops_being_searchable(rig):
    rig["index"].sync(rig["corpus_id"])
    before = rig["search"].search(rig["corpus_id"], "registered office in Mumbai")
    assert any("Mumbai" in hit.text for hit in before.hits)

    (rig["root"] / "office.txt").unlink()
    rig["index"].sync(rig["corpus_id"])

    after = rig["search"].search(rig["corpus_id"], "registered office in Mumbai")
    assert not any("Mumbai" in hit.text for hit in after.hits)
    assert rig["store"].doc_count(rig["corpus_id"]) == 1


def test_deleting_one_of_two_copies_keeps_the_other_searchable(rig):
    shutil.copy(rig["root"] / "office.txt", rig["root"] / "office-copy.txt")
    rig["index"].sync(rig["corpus_id"])

    (rig["root"] / "office.txt").unlink()
    rig["index"].sync(rig["corpus_id"])

    result = rig["search"].search(rig["corpus_id"], "registered office in Mumbai")
    assert any("Mumbai" in hit.text for hit in result.hits)
    assert result.hits[0].citation.relative_path == "office-copy.txt"


def test_search_returns_a_checkable_citation(rig):
    rig["index"].sync(rig["corpus_id"])

    result = rig["search"].search(rig["corpus_id"], "penalty for late delivery")

    assert result.hits
    top = result.hits[0]
    assert "penalty" in top.text.lower()
    assert top.citation.relative_path == "penalty.txt"
    assert top.citation.page_no == 1
    assert top.citation.label.startswith("penalty.txt")


def test_search_without_reranker_is_degraded_not_broken(rig):
    rig["index"].sync(rig["corpus_id"])
    result = rig["search"].search(rig["corpus_id"], "penalty for late delivery")

    assert result.reranked is False
    assert result.degraded_reason == "no_reranker_configured"
    assert result.hits


def test_reranker_reorders_and_a_failing_one_does_not_break_search(rig):
    rig["index"].sync(rig["corpus_id"])

    class ReversingReranker:
        def rerank(self, query, passages, top_n=0):
            rows = [{"index": i, "logit": float(i)} for i in range(len(passages))]
            return sorted(rows, key=lambda r: r["logit"], reverse=True)[: top_n or len(rows)]

    class BrokenReranker:
        def rerank(self, query, passages, top_n=0):
            raise RuntimeError("rerank endpoint down")

    reranked = CorpusSearch(
        store=rig["store"], vector_store=rig["vectors"], embedder=rig["embedder"], reranker=ReversingReranker()
    ).search(rig["corpus_id"], "penalty for late delivery")
    assert reranked.reranked is True

    degraded = CorpusSearch(
        store=rig["store"], vector_store=rig["vectors"], embedder=rig["embedder"], reranker=BrokenReranker()
    ).search(rig["corpus_id"], "penalty for late delivery")
    assert degraded.reranked is False
    assert degraded.degraded_reason == "rerank_error"
    assert degraded.hits, "a dead reranker must not cost the answer"


def test_page_numbers_survive_into_the_citation(rig):
    (rig["root"] / "order.txt").write_text(
        "First page covering the appearance of the parties and the preliminary objections.\f"
        "Second page recording that the interim injunction is granted until further orders.",
        encoding="utf-8",
    )
    rig["index"].sync(rig["corpus_id"])

    result = rig["search"].search(rig["corpus_id"], "interim injunction granted")
    hit = next(h for h in result.hits if h.citation.relative_path == "order.txt")
    assert hit.citation.page_no == 2


def test_unreadable_file_is_reported_not_swallowed(rig):
    (rig["root"] / "blank.txt").write_text("   \n  \n", encoding="utf-8")
    report = rig["index"].sync(rig["corpus_id"])

    assert any(item["relative_path"] == "blank.txt" for item in report.failures)
    failures = rig["store"].extraction_failures(rig["corpus_id"])
    assert any(item["relative_path"] == "blank.txt" for item in failures)


def test_unsupported_file_is_skipped_with_a_reason(rig):
    (rig["root"] / "photo.heic").write_bytes(b"\x00\x01\x02")
    rig["index"].sync(rig["corpus_id"])

    skipped = rig["store"].list_skipped(rig["corpus_id"])
    assert any(item["relative_path"] == "photo.heic" for item in skipped)


def test_attaching_the_same_folder_twice_reuses_the_corpus(rig):
    again = rig["index"].attach(rig["root"])
    assert again == rig["corpus_id"]


def test_empty_query_returns_nothing_rather_than_everything(rig):
    rig["index"].sync(rig["corpus_id"])
    assert rig["search"].search(rig["corpus_id"], "   ").hits == ()


def test_progress_is_reported_while_indexing(rig):
    seen: list[str] = []
    rig["index"].sync(rig["corpus_id"], on_progress=lambda p: seen.append(p.phase))

    assert seen[0] == "scanning"
    assert seen[-1] == "ready"
    assert "indexing" in seen
