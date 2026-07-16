"""List of Dates (chronology) engine (feature-implementation-plan §11).

Dates are found DETERMINISTICALLY in the source text (multi-format regex), so no
date is ever hallucinated — every entry provably appears in a document. The LLM
only summarizes the event around each real date, normalizes it to ISO for
sorting, and filters non-event matches. Entries are sorted chronologically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.providers.base import LLMProvider, Message
# Reuse the review engine's defensive JSON parse + transient-retry wrapper.
from src.review.engine import _complete_with_retry, _extract_json

MAX_HITS = 60
_CONTEXT_CHARS = 200

_MONTHS = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DATE_PATTERNS = [
    r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",                              # 2024-10-15
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",                            # 15/10/2024, 15-10-24
    rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTHS}\.?\s*,?\s+\d{{2,4}}\b",   # 15 October 2024 / 15th Oct 2024
    rf"\b{_MONTHS}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?\s*,?\s+\d{{2,4}}\b",   # October 15, 2024
]
_DATE_RE = re.compile("|".join(_DATE_PATTERNS), re.IGNORECASE)
_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SYSTEM = (
    "You build litigation chronologies. You are given candidate date mentions found in "
    "documents, each with the sentence it appears in. For each candidate: (1) decide if it "
    "denotes a real EVENT date (not a version number, a phone/support token like '24/7', or a "
    "clause/section number); (2) if it is an event, give a normalized ISO date (YYYY-MM-DD) — "
    "infer day/month order from context; if only month/year are known use the first day; (3) write "
    "a concise event summary drawn only from the sentence. Never invent dates or events. Return a "
    'JSON object {"entries":[{"n":1,"is_event":true,"iso_date":"YYYY-MM-DD","event":"..."}, ...]} '
    "with exactly one object per candidate, in the same order."
)


@dataclass
class DateHit:
    raw_date: str
    context: str
    document_id: str
    filename: str
    page_number: int | None


def _sentence_around(text: str, start: int, end: int) -> str:
    """Extract the sentence/line containing the [start, end) match."""
    left_dot = text.rfind(". ", 0, start)
    left_nl = text.rfind("\n", 0, start)
    left = max(left_dot, left_nl)
    left = left + 1 if left != -1 else max(0, start - _CONTEXT_CHARS)
    right_candidates = [r for r in (text.find(". ", end), text.find("\n", end)) if r != -1]
    right = (min(right_candidates) + 1) if right_candidates else min(len(text), end + _CONTEXT_CHARS)
    return text[left:right].strip()


def find_date_hits(chunks: list[dict], *, max_hits: int = MAX_HITS) -> list[DateHit]:
    """Deterministically find date mentions across chunks, with page attribution."""
    hits: list[DateHit] = []
    seen: set[tuple[str, str]] = set()
    for ch in chunks:
        text = ch.get("text") or ""
        for m in _DATE_RE.finditer(text):
            raw = m.group(0).strip()
            ctx = _sentence_around(text, m.start(), m.end())
            key = (raw.lower(), ctx[:80].lower())
            if key in seen:
                continue
            seen.add(key)
            hits.append(
                DateHit(
                    raw_date=raw,
                    context=ctx,
                    document_id=ch.get("document_id", ""),
                    filename=ch.get("filename", ""),
                    page_number=ch.get("page_number"),
                )
            )
            if len(hits) >= max_hits:
                return hits
    return hits


async def build_lod(llm: LLMProvider, hits: list[DateHit]) -> list[dict]:
    """Summarize + normalize + filter date hits, then sort chronologically."""
    if not hits:
        return []

    lines = [f'{i}. DATE="{h.raw_date}" CONTEXT="{h.context[:300]}"' for i, h in enumerate(hits, 1)]
    user = (
        "Candidate date mentions:\n" + "\n".join(lines)
        + f'\n\nReturn a JSON object {{"entries":[...]}} with exactly {len(hits)} entries, same order.'
    )
    messages = [Message(role="system", content=_SYSTEM), Message(role="user", content=user)]
    resp = await _complete_with_retry(llm, messages, max_tokens=3000, temperature=0.0, json_mode=True)

    parsed = _extract_json(resp.content)
    arr = parsed.get("entries") if isinstance(parsed, dict) else None
    if not isinstance(arr, list):
        arr = []

    entries: list[dict] = []
    for i, h in enumerate(hits):
        item = arr[i] if i < len(arr) and isinstance(arr[i], dict) else {}
        # Default to keeping the hit if the model omits is_event (conservative).
        if item.get("is_event", True) is False:
            continue
        iso = str(item.get("iso_date") or "").strip()
        entries.append(
            {
                "date": h.raw_date,
                "iso_date": iso if _ISO_RE.match(iso) else None,
                "event": (str(item.get("event") or "").strip() or h.context[:160]),
                "document_id": h.document_id,
                "filename": h.filename,
                "page_number": h.page_number,
                "snippet": h.context[:240],
            }
        )

    # Chronological sort: entries with a valid ISO date ascending first, then the
    # rest in discovery order (stable sort preserves it).
    entries.sort(key=lambda e: (0, e["iso_date"]) if e["iso_date"] else (1, ""))
    return entries


async def run_lod(llm: LLMProvider, chunks: list[dict], *, max_hits: int = MAX_HITS) -> list[dict]:
    return await build_lod(llm, find_date_hits(chunks, max_hits=max_hits))
