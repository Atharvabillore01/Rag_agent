"""DOCX parser — direct XML via python-docx; preserves headings/tables (§3.2)."""

import io

from .base import ParsedDocument, ParsedPage


def parse_docx(data: bytes) -> ParsedDocument:
    try:
        from docx import Document
        from docx.oxml.ns import qn
    except ImportError as e:
        raise RuntimeError("python-docx not installed. Add it to requirements.txt.") from e

    doc = Document(io.BytesIO(data))
    pages: list[ParsedPage] = []
    current_text: list[str] = []
    current_heading: str | None = None
    page_num = 1

    for block in doc.element.body:
        tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag

        if tag == "p":
            from docx.oxml.parser import OxmlElement
            from docx.text.paragraph import Paragraph

            para = Paragraph(block, doc)
            text = para.text.strip()
            if not text:
                continue

            style = para.style.name if para.style else ""
            if style.startswith("Heading"):
                # Flush previous section as its own "page"
                if current_text:
                    pages.append(
                        ParsedPage(
                            page_number=page_num,
                            text="\n".join(current_text),
                            section_heading=current_heading,
                        )
                    )
                    page_num += 1
                    current_text = []
                current_heading = text
                current_text.append(f"# {text}")
            else:
                current_text.append(text)

        elif tag == "tbl":
            # Render table as Markdown
            from docx.table import Table

            tbl = Table(block, doc)
            rows = []
            for row in tbl.rows:
                cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                rows.append("| " + " | ".join(cells) + " |")
            if rows:
                # Add header separator after first row
                separator = "| " + " | ".join(["---"] * len(tbl.rows[0].cells)) + " |"
                rows.insert(1, separator)
                current_text.append("\n".join(rows))

    if current_text:
        pages.append(
            ParsedPage(
                page_number=page_num,
                text="\n".join(current_text),
                section_heading=current_heading,
            )
        )

    return ParsedDocument(pages=pages)
