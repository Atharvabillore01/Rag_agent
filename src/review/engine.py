"""Parallel Review engine (feature-implementation-plan §3).

Answer M questions across N documents, using ONLY the supplied document text —
no external retrieval, no cross-document leakage. Each document is answered in a
single JSON-mode LLM call; documents are processed concurrently under a
semaphore so a large selection does not fan out unboundedly.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from src.providers.base import LLMProvider, Message

# ~6k tokens of document text per call. Long documents are truncated (flagged in
# the result) rather than silently overflowing the model context window.
DEFAULT_MAX_CHARS = 24_000
DEFAULT_CONCURRENCY = 5
NOT_FOUND = "Not found"

_SYSTEM = (
    "You are a precise document analyst. Answer each question using ONLY the "
    "provided document text. Do not use outside knowledge. If the document does "
    'not contain the answer, respond with exactly "Not found" for that question. '
    "Keep each answer concise (a value, a phrase, or one or two sentences). "
    "Return a JSON object mapping each question key to its answer string."
)

# Backoff schedule (seconds) before retry attempts 2 and 3. A review fans out
# many concurrent LLM calls, so a transient rate-limit / timeout on one document
# is expected under load — retry it rather than surfacing a spurious "Error" cell.
_RETRY_BACKOFF = (0.6, 1.8)
_TRANSIENT_MARKERS = (
    "rate limit", "rate_limit", "429", "timeout", "timed out", "temporarily",
    "overloaded", "unavailable", "503", "502", "500", "connection", "reset",
)


def _is_transient(exc: Exception) -> bool:
    """Heuristic: is this LLM error worth retrying (vs. a hard 4xx/bad request)?"""
    name = type(exc).__name__.lower()
    if any(k in name for k in ("ratelimit", "timeout", "apiconnection", "internalserver", "serviceunavailable")):
        return True
    return any(m in str(exc).lower() for m in _TRANSIENT_MARKERS)


async def _complete_with_retry(llm, messages, *, max_tokens, temperature, json_mode):
    """llm.complete with bounded retry on transient errors (non-transient re-raise immediately)."""
    attempts = len(_RETRY_BACKOFF) + 1
    for attempt in range(attempts):
        try:
            return await llm.complete(
                messages, max_tokens=max_tokens, temperature=temperature, json_mode=json_mode
            )
        except Exception as exc:  # noqa: BLE001
            if attempt == attempts - 1 or not _is_transient(exc):
                raise
            await asyncio.sleep(_RETRY_BACKOFF[attempt])


@dataclass
class ReviewQuestion:
    key: str
    header: str
    question: str


def slugify_key(header: str, index: int) -> str:
    """Derive a stable JSON key from a column header (e.g. 'Principal Amount' ->
    'principal_amount'). Falls back to a positional key for empty/symbolic headers."""
    slug = re.sub(r"[^a-z0-9]+", "_", (header or "").strip().lower()).strip("_")
    return slug or f"q{index + 1}"


def _extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object from an LLM response.

    Handles the common ways models wrap JSON: raw object, fenced ```json blocks,
    or an object embedded in prose. Returns {} if nothing parseable is found so
    callers degrade to per-question defaults rather than crashing.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                obj = json.loads(match.group(0))
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
        return {}


async def answer_document(
    llm: LLMProvider,
    filename: str,
    text: str,
    questions: list[ReviewQuestion],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> tuple[dict[str, str], bool]:
    """Answer all questions for one document. Returns ({key: answer}, truncated)."""
    truncated = len(text) > max_chars
    doc_text = text[:max_chars]
    q_lines = "\n".join(f'- "{q.key}": {q.question}' for q in questions)
    user = (
        f"DOCUMENT (filename: {filename}):\n\"\"\"\n{doc_text}\n\"\"\"\n\n"
        f"QUESTIONS (answer each, keyed exactly as shown):\n{q_lines}\n\n"
        'Return ONLY a JSON object like {"<key>": "<answer>", ...} with one entry '
        "per question key above."
    )
    messages = [
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=user),
    ]
    resp = await _complete_with_retry(llm, messages, max_tokens=1500, temperature=0.0, json_mode=True)
    parsed = _extract_json(resp.content)

    # Guarantee one entry per requested key regardless of what the model returned.
    answers: dict[str, str] = {}
    for q in questions:
        val = parsed.get(q.key)
        answers[q.key] = str(val).strip() if val not in (None, "") else NOT_FOUND
    return answers, truncated


async def run_review(
    llm: LLMProvider,
    docs: list[tuple[str, str, str]],
    questions: list[ReviewQuestion],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, dict]:
    """Run `questions` over each document in `docs`.

    `docs` is a list of (doc_id, filename, text). Returns
    {doc_id: {filename, answers, truncated, error}}. A per-document failure is
    captured in that document's `error` field; it never aborts the whole run.
    """
    if not docs or not questions:
        return {}

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(doc: tuple[str, str, str]) -> tuple[str, dict]:
        doc_id, filename, text = doc
        async with sem:
            try:
                answers, truncated = await answer_document(
                    llm, filename, text, questions, max_chars=max_chars
                )
                return doc_id, {
                    "filename": filename,
                    "answers": answers,
                    "truncated": truncated,
                    "error": None,
                }
            except Exception as exc:  # noqa: BLE001 — isolate one doc's failure
                return doc_id, {
                    "filename": filename,
                    "answers": {q.key: "Error" for q in questions},
                    "truncated": False,
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }

    pairs = await asyncio.gather(*(_one(d) for d in docs))
    return {doc_id: res for doc_id, res in pairs}


_COLUMN_SYSTEM = (
    "You convert a lawyer's free-text request into a structured set of review columns for a "
    "document-comparison table. Infer the distinct columns the user wants even if the request "
    "is terse or has typos. Each column has a short 'header' (2-4 words, Title Case) and a "
    "'question' (a clear instruction to answer for each document). Return a JSON object "
    '{"columns": [{"header": "...", "question": "..."}, ...]} with 1-12 columns and nothing else.'
)


async def suggest_columns(llm: LLMProvider, instruction: str, *, max_columns: int = 12) -> list[dict]:
    """Derive review columns ({header, question}) from a plain-language request."""
    if not instruction or not instruction.strip():
        return []
    messages = [
        Message(role="system", content=_COLUMN_SYSTEM),
        Message(role="user", content=f"Request:\n{instruction.strip()}\n\nReturn the JSON."),
    ]
    resp = await _complete_with_retry(llm, messages, max_tokens=1200, temperature=0.0, json_mode=True)
    parsed = _extract_json(resp.content)
    raw = parsed.get("columns") if isinstance(parsed, dict) else None
    out: list[dict] = []
    if isinstance(raw, list):
        for col in raw[:max_columns]:
            if not isinstance(col, dict):
                continue
            header = str(col.get("header") or "").strip()
            question = str(col.get("question") or "").strip()
            if header and question:
                out.append({"header": header[:120], "question": question[:2000]})
    return out
