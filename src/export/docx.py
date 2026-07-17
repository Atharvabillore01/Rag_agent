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


def redaction_to_docx(name: str, sections: list, unavailable: int = 0) -> bytes:
    """Redacted document export (§28). ``sections`` is a list of
    ``{filename, redacted_text, count}`` — one per source document. ``unavailable``
    is the count of selected documents that could not be re-loaded at export time."""
    d = _doc(name or "Redacted Documents", subtitle="Sensitive values removed")
    if unavailable:
        note = d.add_paragraph(
            f"⚠ {unavailable} selected document(s) were unavailable at export time and are not included."
        )
        if note.runs:
            note.runs[0].italic = True
    for sec in sections or []:
        d.add_heading(str(sec.get("filename") or "Document"), level=2)
        p = d.add_paragraph(f"{sec.get('count', 0)} value(s) redacted")
        if p.runs:
            p.runs[0].italic = True
        for para in (sec.get("redacted_text") or "").split("\n"):
            d.add_paragraph(para)
    # Disclosure: deterministic redaction covers structured identifiers only.
    disc = d.add_paragraph(
        "Note: automated redaction removes structured identifiers (Aadhaar, PAN, GSTIN, IFSC, "
        "credit cards, email, phone). Person names and addresses detected via AI are flagged in "
        "the scan report but are NOT automatically removed here — review manually before sharing."
    )
    if disc.runs:
        disc.runs[0].italic = True
    return _save(d)


_STANCE_LABEL = {
    "admits": "Admits",
    "denies": "Denies",
    "partially_admits": "Partly admits",
    "not_addressed": "Not addressed",
}


def contentions_to_docx(
    name: str,
    issues: list | None,
    results: list | None,
    summary: str | None = None,
) -> bytes:
    """Issue × party contentions matrix, with an optional dispute summary."""
    d = _doc(name or "Contentions Comparison")
    if summary:
        d.add_heading("Summary of dispute", level=2)
        d.add_paragraph(summary)
    issues = issues or []
    results = results or []
    if not issues:
        d.add_paragraph("No distinct contentions could be identified.")
        return _save(d)
    d.add_heading("Issues", level=2)
    headers = ["Issue"] + [str(p.get("filename") or p.get("document_id") or "") for p in results]
    rows: list[list] = []
    for it in issues:
        key = it.get("key")
        cells = [it.get("title", "")]
        for p in results:
            cell = (p.get("stances") or {}).get(key, {}) if isinstance(p, dict) else {}
            label = _STANCE_LABEL.get(cell.get("stance"), "—")
            text = cell.get("text") or ""
            cells.append(f"{label}\n{text}" if text else label)
        rows.append(cells)
    _table(d, headers, rows)
    return _save(d)
