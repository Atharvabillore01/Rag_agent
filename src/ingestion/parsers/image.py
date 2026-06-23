"""Standalone image parser — OCR + caption via vision LLM (§3.2)."""

import base64
import io

from .base import ParsedDocument, ParsedPage


def parse_image(data: bytes, mime: str = "image/png") -> ParsedDocument:
    """Caption the image via Ollama vision model and run pytesseract OCR."""
    caption = _caption_with_ollama(data, mime)
    ocr_text = _ocr(data)

    text_parts = []
    if caption:
        text_parts.append(f"[Figure description]: {caption}")
    if ocr_text:
        text_parts.append(f"[OCR text]: {ocr_text}")

    page = ParsedPage(
        page_number=1,
        text="\n".join(text_parts) if text_parts else "",
        figures=[caption] if caption else [],
    )
    return ParsedDocument(pages=[page])


def _caption_with_ollama(data: bytes, mime: str) -> str:
    """Use Ollama vision model to generate a natural-language figure description."""
    try:
        import httpx

        b64 = base64.b64encode(data).decode()
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llava",
                "prompt": "Describe this image in detail for a document search system. Include any text, charts, diagrams, or figures you see.",
                "images": [b64],
                "stream": False,
            },
            timeout=60.0,
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip()
    except Exception:
        pass
    return ""


def _ocr(data: bytes) -> str:
    """Extract embedded text via pytesseract."""
    try:
        from PIL import Image
        import pytesseract

        img = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(img).strip()
    except Exception:
        return ""
