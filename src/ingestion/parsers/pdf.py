"""PDF parser — fast path (PyMuPDF) for text-native; Marker for complex/scanned (§3.2)."""

import io

from .base import ParsedDocument, ParsedPage


def _has_selectable_text(data: bytes, threshold: float = 0.1) -> bool:
    """Return True if the PDF has enough selectable text to skip OCR."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        total_chars = sum(len(page.get_text()) for page in doc)
        doc.close()
        return total_chars > threshold * len(data)
    except Exception:
        return False


def parse_text_native(data: bytes) -> ParsedDocument:
    """Fast path: PyMuPDF for clean text-native PDFs."""
    import fitz

    doc = fitz.open(stream=data, filetype="pdf")
    pages: list[ParsedPage] = []

    for i, page in enumerate(doc, start=1):
        blocks = page.get_text("blocks")  # preserves reading order
        text = "\n".join(b[4] for b in blocks if b[6] == 0).strip()  # type 0 = text
        pages.append(ParsedPage(page_number=i, text=text))

    doc.close()
    return ParsedDocument(pages=pages)


def parse_with_marker(data: bytes, use_llm: bool = False, ollama_model: str | None = None) -> ParsedDocument:
    """Complex/scanned PDFs via Marker. use_llm=True adds Ollama vision for tables/figures."""
    try:
        from marker.convert import convert_single_pdf
        from marker.models import load_all_models

        models = load_all_models()
        # Marker returns Markdown string and per-page metadata
        full_text, doc_metadata, _ = convert_single_pdf(
            io.BytesIO(data),
            models,
            langs=["English"],
            batch_multiplier=2,
        )

        # Split on form-feed characters that Marker inserts between pages
        raw_pages = full_text.split("\x0c")
        pages = [
            ParsedPage(page_number=i + 1, text=p.strip())
            for i, p in enumerate(raw_pages)
            if p.strip()
        ]
        warnings: list[str] = []
        return ParsedDocument(pages=pages, warnings=warnings)

    except ImportError:
        # Marker not installed — fall back to PyMuPDF with a warning
        doc = parse_text_native(data)
        doc.warnings.append("marker-pdf not installed; fell back to PyMuPDF text extraction")
        return doc


def parse_pdf(data: bytes) -> ParsedDocument:
    """Route to fast or complex path based on content (§3.2.1)."""
    if _has_selectable_text(data):
        return parse_text_native(data)
    return parse_with_marker(data, use_llm=False)
