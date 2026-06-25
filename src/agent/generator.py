"""Streaming answer generator — cited, RBAC-clean, injection-resistant (§4.6, §18)."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from src.agent.prompts import GENERATOR_SYSTEM, GENERATOR_USER
from src.agent.retriever import RetrievedChunk
from src.providers.base import LLMProvider, Message
from src.providers.factory import llm


@dataclass
class Citation:
    document_id: str
    chunk_id: str
    page_number: int | None
    section_heading: str | None


@dataclass
class GeneratorResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    is_partial: bool = False


def _xml_attr(value: str | None) -> str:
    """Escape a string for use as an XML attribute value (single-quoted)."""
    return (value or "").replace("&", "&amp;").replace("'", "&apos;").replace("<", "&lt;")


def _format_chunks(chunks: list[RetrievedChunk], doc_names: dict[str, str] | None = None) -> str:
    """Wrap each chunk in XML tags to make injection attempts structurally visible."""
    parts = []
    for chunk in chunks:
        name = (doc_names or {}).get(chunk.document_id, "")
        name_attr = f" doc_name='{_xml_attr(name)}'" if name else ""
        parts.append(
            f"<chunk id='{_xml_attr(chunk.chunk_id)}' doc='{_xml_attr(chunk.document_id)}'{name_attr} "
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
    answer, citations = _parse_answer_and_citations(response.content, chunks)

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


def _parse_answer_and_citations(
    raw: str, chunks: list[RetrievedChunk]
) -> tuple[str, list[Citation]]:
    """Split the model output into answer text and structured citations."""
    # Case-insensitive split so "Citations:" and "CITATIONS:" both match
    upper = raw.upper()
    marker_pos = upper.find("CITATIONS:")
    if marker_pos != -1:
        answer_part = raw[:marker_pos]
        cit_part = raw[marker_pos + len("CITATIONS:"):]
    else:
        answer_part = raw
        cit_part = ""

    citations: list[Citation] = []
    if cit_part.strip():
        for line in cit_part.strip().splitlines():
            line = line.strip("- ").strip()
            if not line:
                continue
            # Fields are separated by " | " to avoid ambiguity with commas in
            # section headings like "Revenue, Costs, and Margins".
            fields = [f.strip() for f in line.split(" | ")]
            parts: dict[str, str] = {}
            for f in fields:
                if ":" in f:
                    k, _, v = f.partition(":")
                    parts[k.strip().lower()] = v.strip()
            citations.append(
                Citation(
                    document_id=parts.get("document_id", ""),
                    chunk_id=parts.get("chunk_id", ""),
                    page_number=int(parts["page"]) if "page" in parts and parts["page"].strip().isdigit() else None,
                    section_heading=parts.get("section"),
                )
            )
    else:
        # Fallback: cite all chunks that were passed to the model
        citations = [
            Citation(
                document_id=c.document_id,
                chunk_id=c.chunk_id,
                page_number=c.page_number,
                section_heading=c.section_heading,
            )
            for c in chunks
        ]

    return answer_part.strip(), citations
