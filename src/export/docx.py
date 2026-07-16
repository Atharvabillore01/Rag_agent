"""Word (.docx) export for feature outputs (feature-implementation-plan §12).

Deterministic serialization (no LLM) of Parallel Review / Redline / List of Dates
/ Translation results into a well-formatted Word document. Each builder returns
raw `.docx` bytes ready to stream as an attachment.
"""

from __future__ import annotations

import re
from io import BytesIO

from docx import Document

DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def docx_filename(name: str | None) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", (name or "").strip()).strip("_") or "export"
    return f"{slug}.docx"


def _doc(title: str, subtitle: str | None = None) -> Document:
    d = Document()
    d.add_heading(title, level=0)
    if subtitle:
        p = d.add_paragraph(subtitle)
        if p.runs:
            p.runs[0].italic = True
    return d


def _save(d: Document) -> bytes:
    buf = BytesIO()
    d.save(buf)
    return buf.getvalue()


def _table(d: Document, headers: list[str], rows: list[list]) -> None:
    table = d.add_table(rows=1, cols=len(headers))
    try:
        table.style = "Table Grid"  # standard in python-docx's default template
    except Exception:  # pragma: no cover - style missing in some templates
        pass
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = str(h)
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = "—" if val is None or val == "" else str(val)


def review_to_docx(name: str, questions: list | None, document_ids: list | None, results: dict | None) -> bytes:
    d = _doc(name or "Parallel Review")
    questions = questions or []
    results = results or {}
    headers = ["Document"] + [q.get("header", "") for q in questions]
    rows: list[list] = []
    for did in (document_ids or []):
        r = results.get(did, {}) if isinstance(results, dict) else {}
        answers = r.get("answers", {}) if isinstance(r, dict) else {}
        rows.append([r.get("filename", did)] + [answers.get(q.get("key"), "—") for q in questions])
    _table(d, headers, rows)
    return _save(d)


def redline_to_docx(name: str, results: list | None) -> bytes:
    d = _doc(name or "Redline Analysis")
    rows = [
        [r.get("change_type", ""), r.get("change", ""), r.get("consequence", "")]
        for r in (results or [])
    ]
    _table(d, ["Type", "Change", "Consequence"], rows)
    return _save(d)


def lod_to_docx(name: str, results: list | None) -> bytes:
    d = _doc(name or "List of Dates")
    rows = []
    for r in (results or []):
        source = str(r.get("filename", ""))
        if r.get("page_number"):
            source += f" p.{r['page_number']}"
        rows.append([r.get("iso_date") or r.get("date", ""), r.get("event", ""), source])
    _table(d, ["Date", "Event", "Source"], rows)
    return _save(d)


def draft_to_docx(name: str, content: str | None) -> bytes:
    d = _doc(name or "Draft")
    for line in (content or "").split("\n"):
        stripped = line.strip()
        if stripped.startswith("### "):
            d.add_heading(stripped[4:], level=3)
        elif stripped.startswith("## "):
            d.add_heading(stripped[3:], level=2)
        elif stripped.startswith("# "):
            d.add_heading(stripped[2:], level=1)
        else:
            d.add_paragraph(line)
    return _save(d)


def translation_to_docx(filename: str | None, target_language: str | None, result: str | None) -> bytes:
    d = _doc(f"Translation — {filename or 'Document'}", subtitle=f"Translated to {target_language or 'target language'}")
    for para in (result or "").split("\n"):
        d.add_paragraph(para)
    return _save(d)
