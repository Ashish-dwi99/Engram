"""PDF rendering helpers for deterministic deep documentation."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List


def _load_reportlab() -> Dict[str, Any]:
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer
    except Exception as exc:  # pragma: no cover - import error path
        raise RuntimeError(
            "reportlab is required for PDF rendering. Install with: pip install -e '.[docs]'"
        ) from exc

    return {
        "LETTER": LETTER,
        "ParagraphStyle": ParagraphStyle,
        "getSampleStyleSheet": getSampleStyleSheet,
        "inch": inch,
        "canvas": canvas,
        "PageBreak": PageBreak,
        "Paragraph": Paragraph,
        "Preformatted": Preformatted,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Spacer": Spacer,
    }


def render_file_pdf(payload: Dict[str, Any], output_pdf: str | Path) -> int:
    """Render one deep file-guide PDF and return the resulting page count."""
    rl = _load_reportlab()
    styles = _styles(rl)

    out_path = Path(output_pdf)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = rl["SimpleDocTemplate"](
        str(out_path),
        pagesize=rl["LETTER"],
        leftMargin=0.75 * rl["inch"],
        rightMargin=0.75 * rl["inch"],
        topMargin=0.75 * rl["inch"],
        bottomMargin=0.75 * rl["inch"],
        title=f"Deep File Guide: {payload.get('file_path', '')}",
        author="Engram deterministic docgen",
    )

    story: List[Any] = []

    story.append(rl["Paragraph"]("Deep File Guide", styles["title"]))
    story.append(rl["Spacer"](1, 0.15 * rl["inch"]))
    story.append(rl["Paragraph"](f"File: <b>{_escape(payload.get('file_path', ''))}</b>", styles["meta"]))
    story.append(rl["Paragraph"](f"Generated: {_escape(payload.get('generated_at', ''))}", styles["meta"]))
    story.append(rl["Paragraph"](f"Commit: {_escape(payload.get('commit_hash', ''))}", styles["meta"]))
    story.append(rl["Paragraph"](f"Method: {_escape(payload.get('method', ''))}", styles["meta"]))
    story.append(rl["Paragraph"](f"Depth: {_escape(payload.get('doc_depth', ''))}", styles["meta"]))
    story.append(rl["Paragraph"](f"Line count: {_escape(str(payload.get('line_count', '')))}", styles["meta"]))
    story.append(rl["PageBreak"]())

    for section in payload.get("sections", []):
        title = section.get("title", "Section")
        story.append(rl["Paragraph"](_escape(title), styles["h2"]))
        story.append(rl["Spacer"](1, 0.06 * rl["inch"]))

        for paragraph in section.get("paragraphs", []):
            story.append(rl["Paragraph"](_paragraph_text(paragraph), styles["body"]))
            story.append(rl["Spacer"](1, 0.04 * rl["inch"]))

        for block in section.get("code_blocks", []):
            if not str(block).strip():
                continue
            story.append(rl["Preformatted"](str(block), styles["mono"]))
            story.append(rl["Spacer"](1, 0.08 * rl["inch"]))

        story.append(rl["Spacer"](1, 0.1 * rl["inch"]))

    page_count = _build_with_numbered_canvas(doc, story, rl)
    return page_count


def render_index_pdf(index_payload: Dict[str, Any], output_pdf: str | Path) -> int:
    """Render the global index PDF and return page count."""
    rl = _load_reportlab()
    styles = _styles(rl)

    out_path = Path(output_pdf)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = rl["SimpleDocTemplate"](
        str(out_path),
        pagesize=rl["LETTER"],
        leftMargin=0.75 * rl["inch"],
        rightMargin=0.75 * rl["inch"],
        topMargin=0.75 * rl["inch"],
        bottomMargin=0.75 * rl["inch"],
        title="Deep Documentation Index",
        author="Engram deterministic docgen",
    )

    story: List[Any] = []
    story.append(rl["Paragraph"]("Deep Documentation Index", styles["title"]))
    story.append(rl["Spacer"](1, 0.15 * rl["inch"]))
    story.append(rl["Paragraph"](f"Generated: {_escape(index_payload.get('generated_at', ''))}", styles["meta"]))
    story.append(rl["Paragraph"](f"Commit: {_escape(index_payload.get('commit_hash', ''))}", styles["meta"]))
    story.append(rl["Paragraph"](f"Total files: {_escape(str(index_payload.get('total_files', 0)))}", styles["meta"]))
    story.append(rl["Spacer"](1, 0.1 * rl["inch"]))

    story.append(rl["Paragraph"]("What to Read First", styles["h2"]))
    for line in index_payload.get("reading_guide", []):
        story.append(rl["Paragraph"](_paragraph_text(line), styles["body"]))
        story.append(rl["Spacer"](1, 0.03 * rl["inch"]))

    story.append(rl["PageBreak"]())

    groups: Dict[str, List[Dict[str, Any]]] = index_payload.get("groups", {})
    for group_name in sorted(groups):
        story.append(rl["Paragraph"](_escape(group_name), styles["h2"]))
        story.append(rl["Spacer"](1, 0.05 * rl["inch"]))
        for item in groups[group_name]:
            line = (
                f"Source: {_escape(item.get('source_path', ''))}"
                f"<br/>PDF: {_escape(item.get('output_pdf', ''))}"
                f"<br/>Lines: {_escape(str(item.get('line_count', '')))}, "
                f"Pages: {_escape(str(item.get('page_count', '')))}"
            )
            story.append(rl["Paragraph"](line, styles["body"]))
            story.append(rl["Spacer"](1, 0.05 * rl["inch"]))
        story.append(rl["Spacer"](1, 0.08 * rl["inch"]))

    page_count = _build_with_numbered_canvas(doc, story, rl)
    return page_count


def _styles(rl: Dict[str, Any]) -> Dict[str, Any]:
    style_sheet = rl["getSampleStyleSheet"]()
    paragraph_style = rl["ParagraphStyle"]

    return {
        "title": paragraph_style(
            "DocgenTitle",
            parent=style_sheet["Heading1"],
            fontSize=20,
            leading=24,
            spaceAfter=10,
        ),
        "h2": paragraph_style(
            "DocgenHeading2",
            parent=style_sheet["Heading2"],
            fontSize=13,
            leading=16,
            spaceBefore=4,
            spaceAfter=4,
        ),
        "meta": paragraph_style(
            "DocgenMeta",
            parent=style_sheet["BodyText"],
            fontSize=10,
            leading=12,
        ),
        "body": paragraph_style(
            "DocgenBody",
            parent=style_sheet["BodyText"],
            fontSize=10,
            leading=13,
        ),
        "mono": paragraph_style(
            "DocgenMono",
            parent=style_sheet["Code"],
            fontName="Courier",
            fontSize=8,
            leading=10,
            leftIndent=8,
        ),
    }


def _build_with_numbered_canvas(doc: Any, story: List[Any], rl: Dict[str, Any]) -> int:
    canvas_module = rl["canvas"]

    class NumberedCanvas(canvas_module.Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._saved_page_states: List[Dict[str, Any]] = []
            self.page_count: int = 0

        def showPage(self) -> None:  # noqa: N802 - reportlab API
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:  # noqa: N802 - reportlab API
            if not self._saved_page_states or self._saved_page_states[-1].get("_pageNumber") != self._pageNumber:
                self._saved_page_states.append(dict(self.__dict__))

            page_count = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_page_number(page_count)
                super().showPage()
            self.page_count = page_count
            super().save()

        def _draw_page_number(self, page_count: int) -> None:
            self.setFont("Helvetica", 8)
            self.drawRightString(7.5 * rl["inch"], 0.45 * rl["inch"], f"Page {self._pageNumber} of {page_count}")

    holder: Dict[str, Any] = {}

    def canvas_factory(*args: Any, **kwargs: Any) -> NumberedCanvas:
        canvas_obj = NumberedCanvas(*args, **kwargs)
        holder["canvas"] = canvas_obj
        return canvas_obj

    doc.build(story, canvasmaker=canvas_factory)
    return holder["canvas"].page_count if "canvas" in holder else 0


def _escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _paragraph_text(text: Any) -> str:
    value = _escape(text)
    return value.replace("\n", "<br/>")
