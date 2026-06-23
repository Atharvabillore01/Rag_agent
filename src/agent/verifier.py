"""Verifier — checks whether retrieved evidence is sufficient before generation (§4.1, §4.5)."""

import json
from dataclasses import dataclass, field

from src.agent.prompts import PROMPT_VERSION, VERIFIER_SYSTEM, VERIFIER_USER
from src.agent.retriever import RetrievedChunk
from src.providers.base import LLMProvider, Message
from src.providers.factory import llm


@dataclass
class VerifierResult:
    sufficient: bool
    confidence: float
    missing_evidence: list[str] = field(default_factory=list)
    suggested_query_rewrites: list[str] = field(default_factory=list)
    should_retry: bool = False
    prompt_version: str = PROMPT_VERSION


async def verify_retrieval(
    query: str,
    chunks: list[RetrievedChunk],
    current_round: int,
    max_rounds: int,
    provider: LLMProvider | None = None,
) -> VerifierResult:
    """Check if retrieved chunks are sufficient to answer the query."""
    if not chunks:
        return VerifierResult(
            sufficient=False,
            confidence=0.0,
            missing_evidence=["No relevant chunks retrieved"],
            should_retry=current_round < max_rounds,
        )

    provider = provider or llm()
    # Cap per-chunk preview in the verifier — it only needs relevance signals,
    # not the full text.  20 chunks × 400 chars = 8k chars, stays well within
    # any model's context window even at max retrieval rounds.
    _VERIFIER_CHUNK_PREVIEW = 400
    _VERIFIER_MAX_CHUNKS = 20
    shown = chunks[:_VERIFIER_MAX_CHUNKS]
    chunks_text = "\n\n".join(
        f"[Chunk {i+1} | doc={c.document_id} page={c.page_number}]\n{c.text_preview[:_VERIFIER_CHUNK_PREVIEW]}"
        for i, c in enumerate(shown)
    )

    messages = [
        Message(role="system", content=VERIFIER_SYSTEM),
        Message(
            role="user",
            content=VERIFIER_USER.format(
                query=query,
                chunks=chunks_text,
                current_round=current_round,
                max_rounds=max_rounds,
            ),
        ),
    ]

    response = await provider.complete(messages, max_tokens=384, temperature=0.0, json_mode=True)

    try:
        data = json.loads(response.content)
        sufficient = bool(data.get("sufficient", False))
        should_retry = bool(data.get("should_retry", not sufficient)) and current_round < max_rounds

        return VerifierResult(
            sufficient=sufficient,
            confidence=float(data.get("confidence", 0.5)),
            missing_evidence=data.get("missing_evidence", []),
            suggested_query_rewrites=data.get("suggested_query_rewrites", []),
            should_retry=should_retry,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        # Fail closed — if we can't parse the verifier output, treat as insufficient
        return VerifierResult(
            sufficient=False,
            confidence=0.0,
            missing_evidence=["Verifier output unparseable"],
            should_retry=current_round < max_rounds,
        )
