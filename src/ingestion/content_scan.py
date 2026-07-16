"""Upload content validation (G9 — feature-implementation-plan §15).

Uploads were trusted by extension + client-supplied content_type only. This
sniffs the file's actual magic bytes and confirms they match the declared file
type, so a renamed executable/script can't masquerade as a .pdf/.docx/image and
reach the parser.
"""

from __future__ import annotations

import filetype

# Declared file_type (from the router's detector) -> acceptable sniffed MIME types.
# DOCX/PPTX are OOXML zips; `filetype` may report the specific OOXML MIME or the
# generic application/zip depending on version, so both are accepted.
_MAGIC_OK: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    "pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
    },
    "image": {"image/jpeg", "image/png", "image/tiff", "image/webp"},
}


def sniff_mime(data: bytes) -> str | None:
    """Return the MIME guessed from magic bytes, or None if unrecognized."""
    kind = filetype.guess(data)
    return kind.mime if kind else None


def content_matches(data: bytes, file_type: str) -> tuple[bool, str | None]:
    """Return (matches, sniffed_mime).

    `matches` is True only if the bytes' sniffed MIME is an accepted type for the
    declared `file_type`. An unrecognized payload (sniffed None) never matches —
    every supported type (PDF/OOXML/image) has a detectable signature.
    """
    sniffed = sniff_mime(data)
    return sniffed in _MAGIC_OK.get(file_type, set()), sniffed
