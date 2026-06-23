"""File-type router — dispatch to the right parser (§3.2)."""

from .base import ParsedDocument


_MIME_MAP: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "image/jpeg": "image",
    "image/png": "image",
    "image/tiff": "image",
    "image/webp": "image",
}

_EXT_MAP: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".tiff": "image",
    ".tif": "image",
    ".webp": "image",
}


def detect_file_type(filename: str, mime_type: str | None = None) -> str:
    if mime_type and mime_type in _MIME_MAP:
        return _MIME_MAP[mime_type]
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]
    raise ValueError(f"Unsupported file type: filename={filename!r}, mime={mime_type!r}")


def parse_document(data: bytes, file_type: str) -> ParsedDocument:
    match file_type:
        case "pdf":
            from .pdf import parse_pdf
            return parse_pdf(data)
        case "docx":
            from .docx import parse_docx
            return parse_docx(data)
        case "pptx":
            from .pptx import parse_pptx
            return parse_pptx(data)
        case "image":
            from .image import parse_image
            return parse_image(data)
        case _:
            raise ValueError(f"No parser for file_type={file_type!r}")
