#!/usr/bin/env python3
"""Build a single documentation book PDF from per-file doc PDFs + manifest."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    default_manifest = repo_root / "docs" / "pdf" / "manifest.json"
    default_index = repo_root / "docs" / "pdf" / "BOOK_INDEX.pdf"
    default_book = repo_root / "docs" / "pdf" / "BOOK.pdf"

    parser = argparse.ArgumentParser(description="Build single BOOK.pdf from doc manifest + per-file PDFs")
    parser.add_argument("--manifest", default=str(default_manifest), help="Path to docgen manifest.json")
    parser.add_argument("--index-output", default=str(default_index), help="Path for generated index/cover PDF")
    parser.add_argument("--book-output", default=str(default_book), help="Path for final merged book PDF")
    parser.add_argument("--title", default="Engram Deep Documentation Book", help="Book title on cover")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    manifest_path = Path(args.manifest).resolve()
    index_output = Path(args.index_output).resolve()
    book_output = Path(args.book_output).resolve()

    if not manifest_path.exists():
        raise SystemExit(f"manifest not found: {manifest_path}")

    if shutil.which("pdfunite") is None:
        raise SystemExit("pdfunite not found in PATH")

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = sorted(data.get("items", []), key=lambda item: item["source_path"])
    if not items:
        raise SystemExit("manifest contains no items")

    manifest_dir = manifest_path.parent
    missing = [item["output_pdf"] for item in items if not (manifest_dir / item["output_pdf"]).exists()]
    if missing:
        raise SystemExit(f"missing file PDFs ({len(missing)}), first: {missing[0]}")

    cover_pages = 1
    entries_per_page = _entries_per_index_page()
    index_pages = max(1, math.ceil(len(items) / entries_per_page))
    prefix_pages = cover_pages + index_pages

    current_page = prefix_pages + 1
    for item in items:
        item["book_start_page"] = current_page
        current_page += int(item.get("page_count", 0) or 0)

    _render_cover_and_index(
        output_path=index_output,
        title=args.title,
        commit_hash=data.get("commit_hash", "unknown"),
        generated_at=data.get("generated_at", _utc_now()),
        items=items,
        entries_per_page=entries_per_page,
        total_pages=current_page - 1,
    )

    merge_inputs = [str(index_output)] + [str((manifest_dir / item["output_pdf"]).resolve()) for item in items]
    book_output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["pdfunite", *merge_inputs, str(book_output)], check=True)

    print(f"[book] items={len(items)}")
    print(f"[book] index_pdf={index_output}")
    print(f"[book] book_pdf={book_output}")
    print(f"[book] total_pages={current_page - 1}")
    return 0


def _entries_per_index_page() -> int:
    from reportlab.lib.pagesizes import LETTER  # type: ignore

    _, height = LETTER
    top = height - 72
    bottom = 56
    header_space = 48
    row_height = 14
    return max(1, int((top - bottom - header_space) // row_height))


def _render_cover_and_index(
    *,
    output_path: Path,
    title: str,
    commit_hash: str,
    generated_at: str,
    items: List[Dict],
    entries_per_page: int,
    total_pages: int,
) -> None:
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover
        raise SystemExit("reportlab is required. Install with: pip install -e '.[docs]'") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output_path), pagesize=LETTER)
    width, height = LETTER

    # Cover page
    c.setFont("Helvetica-Bold", 22)
    c.drawString(56, height - 96, title)
    c.setFont("Helvetica", 12)
    c.drawString(56, height - 132, f"Generated: {generated_at}")
    c.drawString(56, height - 150, f"Commit: {commit_hash}")
    c.drawString(56, height - 168, f"Files documented: {len(items)}")
    c.drawString(56, height - 186, f"Estimated total pages: {total_pages}")
    c.setFont("Helvetica", 10)
    c.drawString(56, height - 224, "This book combines all deep per-file documentation into one PDF.")
    c.drawString(56, height - 240, "The next pages contain an index with starting page numbers for each source file.")
    _draw_footer(c, 1)
    c.showPage()

    # Index pages start at logical page 2
    logical_page = 2
    chunks = [items[i : i + entries_per_page] for i in range(0, len(items), entries_per_page)]
    if not chunks:
        chunks = [[]]

    for chunk_idx, chunk in enumerate(chunks, start=1):
        y = height - 72
        c.setFont("Helvetica-Bold", 16)
        c.drawString(56, y, f"Index ({chunk_idx}/{len(chunks)})")
        y -= 28

        c.setFont("Helvetica-Bold", 10)
        c.drawString(56, y, "Source file")
        c.drawRightString(width - 120, y, "Start page")
        c.drawRightString(width - 56, y, "Pages")
        y -= 8
        c.line(56, y, width - 56, y)
        y -= 14

        c.setFont("Helvetica", 9)
        for item in chunk:
            source = _ellipsize(item["source_path"], 88)
            c.drawString(56, y, source)
            c.drawRightString(width - 120, y, str(item.get("book_start_page", "")))
            c.drawRightString(width - 56, y, str(item.get("page_count", "")))
            y -= 14

        _draw_footer(c, logical_page)
        logical_page += 1
        c.showPage()

    c.save()


def _draw_footer(c, page: int) -> None:
    c.setFont("Helvetica", 8)
    c.drawRightString(560, 28, f"Page {page}")


def _ellipsize(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
