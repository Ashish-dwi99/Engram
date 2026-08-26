"""Asking a folder a question, and being able to check the answer.

Retrieval here is two stages, because one is measurably not enough. Vector search is
fast and recall-oriented but scores on embedding proximity, which happily ranks a
passage that shares vocabulary with the question above the passage that actually
answers it. A cross-encoder reads the query and the passage together and fixes exactly
that — so the vector stage over-fetches wide and the reranker decides the order.

The reranker is a refinement, never a gate. If it errors or the key is missing, results
still come back in vector order. A folder that answers slightly worse is a degraded
feature; a folder that answers nothing is a broken one.

Every hit carries its citation — file, page, and the character span within the page —
because the value of this feature is not that it answers, it is that the answer can be
checked against the document in one click.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from dhee.corpus.store import ChunkRecord, CorpusStore

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 8
# Over-fetch before reranking. The cross-encoder can only reorder what the vector stage
# handed it, so the recall ceiling of the whole pipeline is set right here.
DEFAULT_CANDIDATE_MULTIPLIER = 6
MAX_CANDIDATES = 100
# Below this the passage is almost certainly unrelated; returning it as a citation
# would be worse than returning nothing, because a bad citation is still a citation.
MIN_VECTOR_SCORE = 0.15


@dataclass(frozen=True, slots=True)
class Citation:
    relative_path: str
    page_no: int
    blob_sha: str
    char_start: int
    char_end: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "page_no": self.page_no,
            "blob_sha": self.blob_sha,
            "char_start": self.char_start,
            "char_end": self.char_end,
        }

    @property
    def label(self) -> str:
        name = self.relative_path.rsplit("/", 1)[-1]
        return f"{name} · p.{self.page_no}" if self.page_no else name


@dataclass(frozen=True, slots=True)
class SearchHit:
    text: str
    score: float
    citation: Citation
    vector_score: float = 0.0
    reranked: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "score": round(self.score, 6),
            "vector_score": round(self.vector_score, 6),
            "reranked": self.reranked,
            "citation": self.citation.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class SearchResult:
    query: str
    corpus_id: str
    hits: tuple[SearchHit, ...] = ()
    candidates_considered: int = 0
    reranked: bool = False
    degraded_reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "corpus_id": self.corpus_id,
            "hits": [hit.as_dict() for hit in self.hits],
            "candidates_considered": self.candidates_considered,
            "reranked": self.reranked,
            "degraded_reason": self.degraded_reason,
        }


class CorpusSearch:
    """Vector recall, then cross-encoder precision, then a citation for each hit."""

    def __init__(
        self,
        *,
        store: CorpusStore,
        vector_store: Any,
        embedder: Any,
        reranker: Optional[Any] = None,
        candidate_multiplier: int = DEFAULT_CANDIDATE_MULTIPLIER,
    ):
        self.store = store
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker
        self.candidate_multiplier = max(1, candidate_multiplier)

    def search(
        self,
        corpus_id: str,
        query: str,
        *,
        limit: int = DEFAULT_LIMIT,
        min_score: float = MIN_VECTOR_SCORE,
    ) -> SearchResult:
        cleaned = " ".join(str(query or "").split())
        if not cleaned:
            return SearchResult(query="", corpus_id=corpus_id)

        candidates = min(MAX_CANDIDATES, max(limit, limit * self.candidate_multiplier))
        vector = self._embed_query(cleaned)
        raw = self.vector_store.search(query=cleaned, vectors=vector, limit=candidates)

        # Scope and hydrate in one step. Anything whose file has left the corpus simply
        # does not resolve, so a deleted document cannot be cited even while its vector
        # is still in the collection.
        scored: Dict[str, float] = {}
        for item in raw:
            chunk_id = _result_id(item)
            score = _result_score(item)
            if chunk_id and score >= min_score:
                scored[chunk_id] = max(score, scored.get(chunk_id, 0.0))

        resolved = self.store.resolve_chunks(corpus_id, list(scored))
        if not resolved:
            return SearchResult(query=cleaned, corpus_id=corpus_id, candidates_considered=len(raw))

        ordered = sorted(resolved.values(), key=lambda record: scored.get(record.chunk_id, 0.0), reverse=True)

        reranked_hits, degraded = self._rerank(cleaned, ordered, scored, limit)
        return SearchResult(
            query=cleaned,
            corpus_id=corpus_id,
            hits=tuple(reranked_hits),
            candidates_considered=len(ordered),
            reranked=not degraded,
            degraded_reason=degraded,
        )

    # -------------------------------------------------------------- internals

    def _embed_query(self, query: str) -> List[float]:
        """Embed for the query side when the model distinguishes the two roles."""
        embed_query = getattr(self.embedder, "embed_query", None)
        if callable(embed_query):
            return embed_query(query)
        return self.embedder.embed(query)

    def _rerank(
        self,
        query: str,
        records: Sequence[ChunkRecord],
        vector_scores: Dict[str, float],
        limit: int,
    ) -> tuple[List[SearchHit], str]:
        def as_hits(items: Sequence[ChunkRecord], scores: Dict[str, float], reranked: bool) -> List[SearchHit]:
            return [
                SearchHit(
                    text=record.text,
                    score=scores.get(record.chunk_id, 0.0),
                    vector_score=vector_scores.get(record.chunk_id, 0.0),
                    reranked=reranked,
                    citation=Citation(
                        relative_path=record.relative_path,
                        page_no=record.page_no,
                        blob_sha=record.blob_sha,
                        char_start=record.char_start,
                        char_end=record.char_end,
                    ),
                )
                for record in items[:limit]
            ]

        if self.reranker is None:
            return as_hits(records, vector_scores, reranked=False), "no_reranker_configured"

        try:
            rankings = self.reranker.rerank(query, [record.text for record in records], top_n=limit)
        except Exception as exc:  # noqa: BLE001 - degrade, never fail the search
            logger.warning("corpus rerank failed, falling back to vector order: %s", exc)
            return as_hits(records, vector_scores, reranked=False), "rerank_error"

        if not rankings:
            return as_hits(records, vector_scores, reranked=False), "rerank_empty"

        reordered: List[ChunkRecord] = []
        scores: Dict[str, float] = {}
        for row in rankings:
            index = int(row.get("index", -1))
            if not 0 <= index < len(records):
                continue
            record = records[index]
            reordered.append(record)
            scores[record.chunk_id] = float(row.get("logit", 0.0))

        if not reordered:
            return as_hits(records, vector_scores, reranked=False), "rerank_unusable"
        return as_hits(reordered, scores, reranked=True), ""


def _result_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("id") or item.get("chunk_id") or "")
    return str(getattr(item, "id", "") or "")


def _result_score(item: Any) -> float:
    if isinstance(item, dict):
        return float(item.get("score") or 0.0)
    return float(getattr(item, "score", 0.0) or 0.0)
