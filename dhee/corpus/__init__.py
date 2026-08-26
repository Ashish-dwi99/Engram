"""Dhee's document corpus — a third lane, beside beliefs and world memory.

Belief memory answers "what is true about the user and the work". A corpus answers
"what does this folder of documents say", and the two must not share a store: Dhee's
quality pipeline deliberately treats document chunks as noise so that a thousand
fragments of a PDF never drown a handful of real beliefs. This package is where those
fragments are supposed to live instead.

Typical use::

    from dhee.corpus import CorpusIndex, CorpusSearch, CorpusStore

    index = CorpusIndex(store=store, vector_store=vectors, embedder=embedder,
                        extractor=my_ocr_extractor)
    corpus_id = index.attach("~/Documents/Cases")
    index.sync(corpus_id)

    hits = CorpusSearch(store=store, vector_store=vectors, embedder=embedder,
                        reranker=reranker).search(corpus_id, "what is the penalty clause?")

Extraction is injected, never imported: OCR belongs to the host application, so Dhee
still installs and runs on its own.
"""

from dhee.corpus.extract import (
    Chunk,
    ExtractedDoc,
    ExtractedLine,
    ExtractedPage,
    ExtractorChain,
    PlainTextExtractor,
    TextExtractor,
    chunk_document,
)
from dhee.corpus.index import CorpusIndex, SyncProgress, SyncReport
from dhee.corpus.search import Citation, CorpusSearch, SearchHit, SearchResult
from dhee.corpus.store import ChunkRecord, CorpusRecord, CorpusStore
from dhee.corpus.tree import (
    BlobEntry,
    FolderDiff,
    FolderSnapshot,
    changed_subtrees,
    diff,
    scan,
)

__all__ = [
    "BlobEntry",
    "Chunk",
    "ChunkRecord",
    "Citation",
    "CorpusIndex",
    "CorpusRecord",
    "CorpusSearch",
    "CorpusStore",
    "ExtractedDoc",
    "ExtractedLine",
    "ExtractedPage",
    "ExtractorChain",
    "FolderDiff",
    "FolderSnapshot",
    "PlainTextExtractor",
    "SearchHit",
    "SearchResult",
    "SyncProgress",
    "SyncReport",
    "TextExtractor",
    "changed_subtrees",
    "chunk_document",
    "diff",
    "scan",
]
