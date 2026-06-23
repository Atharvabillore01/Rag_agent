"""PPTX parser — one ParsedPage per slide + speaker notes (§3.2)."""

import io

from .base import ParsedDocument, ParsedPage


def parse_pptx(data: bytes) -> ParsedDocument:
    try:
        from pptx import Presentation
    except ImportError as e:
        raise RuntimeError("python-pptx not installed. Add it to requirements.txt.") from e

    prs = Presentation(io.BytesIO(data))
    pages: list[ParsedPage] = []

    for i, slide in enumerate(prs.slides, start=1):
        title_shape = slide.shapes.title
        title = title_shape.text.strip() if title_shape and title_shape.has_text_frame else None

        body_parts: list[str] = []
        for shape in slide.shapes:
            if shape == title_shape:
                continue
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        body_parts.append(text)
            if shape.has_table:
                rows = []
                for row in shape.table.rows:
                    cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    rows.append("| " + " | ".join(cells) + " |")
                if rows:
                    sep = "| " + " | ".join(["---"] * len(shape.table.columns)) + " |"
                    rows.insert(1, sep)
                    body_parts.append("\n".join(rows))

        # Speaker notes
        notes_text = ""
        if slide.has_notes_slide:
            notes_frame = slide.notes_slide.notes_text_frame
            if notes_frame:
                notes_text = notes_frame.text.strip()

        full_text = (f"## {title}\n\n" if title else "") + "\n".join(body_parts)
        if notes_text:
            full_text += f"\n\n**Speaker notes:** {notes_text}"

        pages.append(
            ParsedPage(
                page_number=i,
                text=full_text.strip(),
                section_heading=title,
            )
        )

    return ParsedDocument(pages=pages)
