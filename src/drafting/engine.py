"""Drafting assistant engine (feature-implementation-plan §13).

Retrieval-grounded drafting: given an instruction and a set of source documents,
produce a complete document in Markdown, grounded in and cited to those sources.
Source documents are numbered so the model can cite them inline as [n]; a trailing
SOURCES line is parsed into doc-level citations and stripped from the output.
"""

from __future__ import annotations

import re

from src.providers.base import LLMProvider, Message
# Reuse the review engine's transient-retry wrapper.
from src.review.engine import _complete_with_retry

_MAX_DOC_CHARS = 8000  # per source document included in the prompt

_SYSTEM = (
    "You are an expert professional and legal drafter. Using ONLY the provided SOURCE DOCUMENTS and "
    "the user's INSTRUCTION, produce a complete, well-structured document in Markdown. Ground every "
    "factual claim in the sources; do NOT invent facts, figures, dates, amounts, or names that are not "
    "supported by the sources or the instruction. Where a claim relies on a source, cite it inline as "
    "[n] using that source's number. Use clear Markdown headings and a professional tone. At the very "
    "end, on its own line, write 'SOURCES: 1, 2' listing the source-document numbers you relied on "
    "(or 'SOURCES: none' if you used none)."
)

_SOURCES_RE = re.compile(r"(?im)^[ \t>*-]*SOURCES:\s*(.*)$")


def _format_sources(docs: list[tuple[str, str, str]]) -> str:
    parts = []
    for i, (_doc_id, filename, text) in enumerate(docs, 1):
        parts.append(f'[{i}] {filename}\n"""\n{text[:_MAX_DOC_CHARS]}\n"""')
    return "\n\n".join(parts)


def _parse_sources(content: str, docs: list[tuple[str, str, str]]) -> tuple[str, list[dict]]:
    """Split off the trailing SOURCES line → (body, doc-level citations)."""
    match = _SOURCES_RE.search(content or "")
    numbers: list[int] = []
    if match:
        raw = match.group(1).strip()
        if raw.lower() != "none":
            numbers = [int(n) for n in re.findall(r"\d+", raw)]
        body = content[: match.start()].rstrip()
    else:
        body = (content or "").rstrip()

    citations: list[dict] = []
    seen: set[int] = set()
    for n in numbers:
        if 1 <= n <= len(docs) and n not in seen:
            seen.add(n)
            doc_id, filename, _ = docs[n - 1]
            citations.append({"number": n, "document_id": doc_id, "filename": filename})
    return body.strip(), citations


async def generate_draft(
    llm: LLMProvider,
    instruction: str,
    docs: list[tuple[str, str, str]],
) -> dict:
    """Return {content, citations}. `docs` is a list of (doc_id, filename, text)."""
    if docs:
        user = (
            f"INSTRUCTION:\n{instruction}\n\n"
            f"SOURCE DOCUMENTS:\n{_format_sources(docs)}\n\n"
            "Draft the document now. Cite sources inline as [n] and end with the SOURCES line."
        )
    else:
        user = (
            f"INSTRUCTION:\n{instruction}\n\n"
            "No source documents were provided; draft from the instruction alone. "
            "End with 'SOURCES: none'."
        )
    messages = [Message(role="system", content=_SYSTEM), Message(role="user", content=user)]
    resp = await _complete_with_retry(llm, messages, max_tokens=4000, temperature=0.2, json_mode=False)
    content, citations = _parse_sources(resp.content or "", docs)
    return {"content": content, "citations": citations}
