"""Turning a file into pages of text, and pages of text into citable chunks.

Two responsibilities that stay deliberately separate:

**Extraction** is pluggable and lives outside Dhee. Dhee ships a default that reads
plain text and PDFs that already carry a text layer — enough to be useful alone, which
is the standing rule for this package. Anything harder (a scan, a photograph of a page,
a Devanagari order) needs OCR, and OCR is a 220MB bundle that belongs to the host
application, not to a library. So `TextExtractor` is a Protocol the host implements and
injects. Dhee never imports the host.

**Chunking** is Dhee's, and it is page-aware on purpose. A retrieval hit is only worth
as much as the citation attached to it: "this is in the folder somewhere" is not an
answer, "page 4 of the March order" is. So chunks never straddle a page boundary, and
every chunk carries the page it came from all the way through to the answer.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

# Roughly 300 tokens. Small enough that a hit points at a paragraph rather than a page,
# large enough that a clause keeps the sentences that qualify it.
DEFAULT_CHUNK_CHARS = 1200
# One or two sentences of carry-over, so a clause split across a boundary is still
# retrievable from either side.
DEFAULT_CHUNK_OVERLAP_CHARS = 160
MIN_CHUNK_CHARS = 60

EXTRACTION_OK = "extracted"
EXTRACTION_EMPTY = "empty"
EXTRACTION_UNSUPPORTED = "unsupported"
EXTRACTION_FAILED = "failed"

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")
_WHITESPACE = re.compile(r"[ \t]+")


@dataclass(frozen=True, slots=True)
class ExtractedLine:
    """One recognised line, and where it sat on the page.

    The box is optional because a text-layer PDF has no geometry worth keeping, but an
    OCR engine does — and a citation into a scan should be able to highlight the region
    it came from rather than only name the page.
    """

    text: str
    confidence: float = 1.0
    box: Optional[Tuple[float, float, float, float]] = None


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_no: int
    text: str
    lines: Tuple[ExtractedLine, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass(frozen=True, slots=True)
class ExtractedDoc:
    """Everything one file yielded, plus an honest account of how it went."""

    pages: Tuple[ExtractedPage, ...] = ()
    engine: str = ""
    status: str = EXTRACTION_OK
    error: str = ""
    was_scanned: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text.strip())

    @property
    def is_usable(self) -> bool:
        return self.status == EXTRACTION_OK and bool(self.text.strip())

    @classmethod
    def failure(cls, reason: str, *, engine: str = "", status: str = EXTRACTION_FAILED) -> "ExtractedDoc":
        return cls(engine=engine, status=status, error=reason)


@runtime_checkable
class TextExtractor(Protocol):
    """What the host plugs in. One method to decide, one to do."""

    def supports(self, path: Path) -> bool:
        ...

    def extract(self, path: Path) -> ExtractedDoc:
        ...


@dataclass(frozen=True, slots=True)
class Chunk:
    """A retrievable span, addressed by the content it came from.

    ``chunk_id`` is derived from the blob hash and the chunk's own text, so the same
    passage in two copies of the same document is one chunk with one embedding, and a
    chunk's identity never depends on the path it was found at.
    """

    chunk_id: str
    blob_sha: str
    chunk_index: int
    page_no: int
    text: str
    char_start: int
    char_end: int

    @property
    def char_count(self) -> int:
        return len(self.text)


def chunk_id_for(blob_sha: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256()
    digest.update(blob_sha.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(chunk_index).encode("ascii"))
    digest.update(b"\0")
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def normalise_text(value: str) -> str:
    """Collapse the noise OCR and PDF layers add, keeping paragraph structure.

    Runs of spaces become one space and trailing space is dropped, because they change
    a chunk's hash without changing its meaning — and a chunk whose hash moves for no
    reason is a chunk that gets re-embedded for no reason.
    """
    lines = [_WHITESPACE.sub(" ", line).strip() for line in value.splitlines()]
    collapsed: List[str] = []
    blank_run = 0
    for line in lines:
        if line:
            blank_run = 0
            collapsed.append(line)
        else:
            blank_run += 1
            if blank_run == 1:
                collapsed.append("")
    return "\n".join(collapsed).strip()


def chunk_page(
    *,
    blob_sha: str,
    page: ExtractedPage,
    start_index: int,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> List[Chunk]:
    """Split one page, preferring to break where the author already broke.

    Paragraph boundaries first, then sentence boundaries, then a hard cut. Breaking
    mid-sentence is the worst outcome for retrieval quality, so it is what we fall back
    to rather than what we do.
    """
    text = normalise_text(page.text)
    if len(text) < MIN_CHUNK_CHARS:
        return []

    spans = _split_spans(text, max_chars=max_chars, overlap_chars=overlap_chars)
    chunks: List[Chunk] = []
    for offset, (start, end) in enumerate(spans):
        body = text[start:end].strip()
        if len(body) < MIN_CHUNK_CHARS:
            continue
        index = start_index + len(chunks)
        chunks.append(
            Chunk(
                chunk_id=chunk_id_for(blob_sha, index, body),
                blob_sha=blob_sha,
                chunk_index=index,
                page_no=page.page_no,
                text=body,
                char_start=start,
                char_end=end,
            )
        )
    return chunks


def chunk_document(
    *,
    blob_sha: str,
    doc: ExtractedDoc,
    max_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> List[Chunk]:
    chunks: List[Chunk] = []
    for page in doc.pages:
        chunks.extend(
            chunk_page(
                blob_sha=blob_sha,
                page=page,
                start_index=len(chunks),
                max_chars=max_chars,
                overlap_chars=overlap_chars,
            )
        )
    return chunks


def _split_spans(text: str, *, max_chars: int, overlap_chars: int) -> List[Tuple[int, int]]:
    if len(text) <= max_chars:
        return [(0, len(text))]

    boundaries = _candidate_boundaries(text)
    spans: List[Tuple[int, int]] = []
    start = 0
    length = len(text)

    while start < length:
        hard_end = min(start + max_chars, length)
        if hard_end >= length:
            spans.append((start, length))
            break

        # The last boundary that fits, provided it leaves a chunk worth having.
        cut = max(
            (pos for pos in boundaries if start + MIN_CHUNK_CHARS < pos <= hard_end),
            default=hard_end,
        )
        spans.append((start, cut))
        next_start = cut - overlap_chars
        start = cut if next_start <= start else next_start

    return spans


def _candidate_boundaries(text: str) -> List[int]:
    """Offsets it is safe to break at, best first — paragraphs, then sentences."""
    positions = {match.end() for match in _PARAGRAPH_BREAK.finditer(text)}
    positions.update(match.end() for match in _SENTENCE_END.finditer(text))
    positions.add(len(text))
    return sorted(positions)


class PlainTextExtractor:
    """Dhee's built-in floor: text files, and PDFs that already carry a text layer.

    This exists so the corpus works with no host and no bundle at all. It deliberately
    does not attempt OCR — a scanned page returns ``EXTRACTION_EMPTY`` with a reason
    rather than silently indexing nothing, so the caller can see that a real extractor
    is needed rather than wonder why the document is unsearchable.
    """

    TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml", ".log"})
    PDF_SUFFIXES = frozenset({".pdf"})

    name = "plain_text"

    def supports(self, path: Path) -> bool:
        suffix = path.suffix.lower()
        return suffix in self.TEXT_SUFFIXES or suffix in self.PDF_SUFFIXES

    def extract(self, path: Path) -> ExtractedDoc:
        suffix = path.suffix.lower()
        if suffix in self.TEXT_SUFFIXES:
            return self._extract_text(path)
        if suffix in self.PDF_SUFFIXES:
            return self._extract_pdf(path)
        return ExtractedDoc.failure(f"unsupported suffix {suffix}", engine=self.name, status=EXTRACTION_UNSUPPORTED)

    def _extract_text(self, path: Path) -> ExtractedDoc:
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ExtractedDoc.failure(str(exc), engine=self.name)
        body = normalise_text(raw)
        if not body:
            return ExtractedDoc(engine=self.name, status=EXTRACTION_EMPTY, error="file is empty")
        return ExtractedDoc(pages=(ExtractedPage(page_no=1, text=body),), engine=self.name)

    def _extract_pdf(self, path: Path) -> ExtractedDoc:
        try:
            from pypdf import PdfReader
        except ImportError:
            return ExtractedDoc.failure(
                "pypdf is not installed, so PDF text extraction is unavailable",
                engine=self.name,
                status=EXTRACTION_UNSUPPORTED,
            )
        try:
            reader = PdfReader(str(path))
            pages: List[ExtractedPage] = []
            for number, page in enumerate(reader.pages, start=1):
                body = normalise_text(page.extract_text() or "")
                if body:
                    pages.append(ExtractedPage(page_no=number, text=body))
        except Exception as exc:  # pypdf raises a wide range on damaged files
            return ExtractedDoc.failure(f"could not read pdf: {exc}", engine=self.name)

        if not pages:
            # Almost always a scan. Say so, because the fix is an OCR extractor.
            return ExtractedDoc(
                engine=self.name,
                status=EXTRACTION_EMPTY,
                error="pdf has no text layer — it is probably scanned and needs OCR",
                was_scanned=True,
            )
        return ExtractedDoc(pages=tuple(pages), engine=self.name)


class ExtractorChain:
    """Try each extractor in order and take the first that both supports and succeeds.

    A registry rather than branching, so the host adds OCR by putting it at the front
    of the tuple. Falling through on an *unusable* result (not merely an unsupported
    one) is what lets a text-layer reader sit ahead of an expensive OCR pass: the cheap
    engine gets first refusal, and the expensive one only runs when the cheap one came
    back empty.
    """

    def __init__(self, extractors: Sequence[TextExtractor]):
        if not extractors:
            raise ValueError("ExtractorChain needs at least one extractor")
        self._extractors = tuple(extractors)

    def supports(self, path: Path) -> bool:
        return any(extractor.supports(path) for extractor in self._extractors)

    def extract(self, path: Path) -> ExtractedDoc:
        last: Optional[ExtractedDoc] = None
        for extractor in self._extractors:
            if not extractor.supports(path):
                continue
            result = extractor.extract(path)
            if result.is_usable:
                return result
            last = last or result
        return last or ExtractedDoc.failure(
            f"no extractor handles {path.suffix or 'this file'}",
            status=EXTRACTION_UNSUPPORTED,
        )
