"""Streaming answer generator — cited, RBAC-clean, injection-resistant (§4.6, §18)."""

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from src.agent.prompts import GENERATOR_SYSTEM, GENERATOR_USER
from src.agent.retriever import RetrievedChunk
from src.providers.base import LLMProvider, Message
from src.providers.factory import llm

# How many chunks to cite when the model emits no SOURCES line (precise fallback,
# not "cite everything").
_FALLBACK_CITATION_COUNT = 3
_SNIPPET_CHARS = 240


@dataclass
class Citation:
    document_id: str
    chunk_id: str
    page_number: int | None
    section_heading: str | None
    number: int | None = None          # the [n] marker this source corresponds to
    filename: str | None = None        # human-readable source name (for the UI)
    snippet: str | None = None         # short preview of the cited text


@dataclass
class GeneratorResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    is_partial: bool = False


def _xml_attr(value: str | None) -> str:
    """Escape a string for use as an XML attribute value (single-quoted)."""
    return (value or "").replace("&", "&amp;").replace("'", "&apos;").replace("<", "&lt;")


def _citation_from_chunk(
    chunk: RetrievedChunk, number: int, doc_names: dict[str, str] | None
) -> Citation:
    return Citation(
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        page_number=chunk.page_number,
        section_heading=chunk.section_heading,
        number=number,
        filename=(doc_names or {}).get(chunk.document_id),
        snippet=(chunk.text_preview or "")[:_SNIPPET_CHARS].strip() or None,
    )


def _format_chunks(chunks: list[RetrievedChunk], doc_names: dict[str, str] | None = None) -> str:
    """Wrap each chunk in XML tags (injection-visible) and number it for citation."""
    parts = []
    for i, chunk in enumerate(chunks, 1):
        name = (doc_names or {}).get(chunk.document_id, "")
        name_attr = f" doc_name='{_xml_attr(name)}'" if name else ""
        parts.append(
            f"<chunk n='{i}' id='{_xml_attr(chunk.chunk_id)}' doc='{_xml_attr(chunk.document_id)}'{name_attr} "
            f"page='{chunk.page_number}' section='{_xml_attr(chunk.section_heading)}'>\n"
            f"{chunk.text_preview}\n"
            f"</chunk>"
        )
    return "\n\n".join(parts)


async def generate_answer(
    question: str,
    chunks: list[RetrievedChunk],
    planner_summary: str = "",
    provider: LLMProvider | None = None,
    doc_names: dict[str, str] | None = None,
) -> GeneratorResult:
    """Non-streaming generation — returns full answer with citations."""
    provider = provider or llm()

    messages = [
        Message(role="system", content=GENERATOR_SYSTEM),
        Message(
            role="user",
            content=GENERATOR_USER.format(
                question=question,
                chunks=_format_chunks(chunks, doc_names),
                planner_summary=planner_summary or "Single-hop query.",
            ),
        ),
    ]

    response = await provider.complete(messages, max_tokens=2048, temperature=0.0)
    answer, citations = _parse_answer_and_citations(response.content, chunks, doc_names)

    return GeneratorResult(answer=answer, citations=citations)


async def stream_answer(
    question: str,
    chunks: list[RetrievedChunk],
    planner_summary: str = "",
    provider: LLMProvider | None = None,
    doc_names: dict[str, str] | None = None,
) -> AsyncGenerator[str, None]:
    """Token-by-token streaming generation (§4.3)."""
    provider = provider or llm()

    messages = [
        Message(role="system", content=GENERATOR_SYSTEM),
        Message(
            role="user",
            content=GENERATOR_USER.format(
                question=question,
                chunks=_format_chunks(chunks, doc_names),
                planner_summary=planner_summary or "Single-hop query.",
            ),
        ),
    ]

    async for token in provider.stream(messages, max_tokens=2048, temperature=0.0):
        yield token


_SOURCES_RE = re.compile(r"(?im)^[ \t>*-]*SOURCES:\s*(.*)$")


def _parse_answer_and_citations(
    raw: str,
    chunks: list[RetrievedChunk],
    doc_names: dict[str, str] | None = None,
) -> tuple[str, list[Citation]]:
    """Split model output into displayed answer + structured citations.

    Reads the trailing `SOURCES: 1, 3` line, maps those chunk numbers back to the
    retrieved chunks (enriching each citation with filename/page/snippet), strips
    the SOURCES line from the answer, and — if the model emitted none — falls back
    to the top few chunks rather than citing everything.
    """
    match = _SOURCES_RE.search(raw)
    numbers: list[int] = []
    if match:
        raw_list = match.group(1).strip()
        if raw_list.lower() != "none":
            # Accept "1, 3", "[1] [3]", "1 3", etc.
            numbers = [int(n) for n in re.findall(r"\d+", raw_list)]
        # Strip the SOURCES line (and anything after it) from the displayed answer.
        answer_part = raw[: match.start()].rstrip()
    else:
        answer_part = raw.rstrip()

    citations: list[Citation] = []
    seen: set[str] = set()
    for n in numbers:
        if 1 <= n <= len(chunks):
            chunk = chunks[n - 1]
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            citations.append(_citation_from_chunk(chunk, n, doc_names))

    if not citations and chunks:
        # Precise fallback: the top few retrieved chunks (already rerank-ordered),
        # not the entire candidate set.
        citations = [
            _citation_from_chunk(c, i + 1, doc_names)
            for i, c in enumerate(chunks[:_FALLBACK_CITATION_COUNT])
        ]

    return answer_part.strip(), citations
