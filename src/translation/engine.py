"""Document translation engine (feature-implementation-plan §9).

Splits long document text into line-bounded segments, translates each into the
target language (bounded concurrency + transient-retry), and rejoins in order.
Plain-text output — the model is told to preserve names, numbers, dates, and
line breaks and to emit only the translation.
"""

from __future__ import annotations

import asyncio

from src.providers.base import LLMProvider, Message
# Reuse the review engine's transient-retry wrapper.
from src.review.engine import _complete_with_retry

MAX_CHARS_PER_CALL = 6000
CONCURRENCY = 4

_SYSTEM_TMPL = (
    "You are a professional translator. Translate the user's text into {target}. "
    "Preserve meaning, proper names, numbers, dates, and line breaks. Do not add "
    "notes, explanations, or preamble — output only the translation."
)


def _split(text: str, max_chars: int = MAX_CHARS_PER_CALL) -> list[str]:
    """Split text into ordered segments no larger than max_chars, on line boundaries."""
    lines = (text or "").split("\n")
    segments: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for ln in lines:
        add = len(ln) + 1
        if cur and cur_len + add > max_chars:
            segments.append("\n".join(cur))
            cur, cur_len = [], 0
        if add > max_chars:
            # A single overlong line — flush, then hard-split it.
            if cur:
                segments.append("\n".join(cur))
                cur, cur_len = [], 0
            for i in range(0, len(ln), max_chars):
                segments.append(ln[i : i + max_chars])
        else:
            cur.append(ln)
            cur_len += add
    if cur:
        segments.append("\n".join(cur))
    return [s for s in segments if s.strip()]


async def _translate_segment(llm: LLMProvider, segment: str, target_language: str) -> str:
    messages = [
        Message(role="system", content=_SYSTEM_TMPL.format(target=target_language)),
        Message(role="user", content=segment),
    ]
    resp = await _complete_with_retry(
        llm, messages, max_tokens=4000, temperature=0.0, json_mode=False
    )
    return (resp.content or "").strip()


async def translate_text(
    llm: LLMProvider,
    text: str,
    target_language: str,
    *,
    max_chars: int = MAX_CHARS_PER_CALL,
    concurrency: int = CONCURRENCY,
) -> str:
    """Translate `text` into `target_language`, segmenting long input."""
    segments = _split(text, max_chars)
    if not segments:
        return ""

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(seg: str) -> str:
        async with sem:
            return await _translate_segment(llm, seg, target_language)

    parts = await asyncio.gather(*(_one(s) for s in segments))
    return "\n".join(parts).strip()
