"""Contentions Comparison engine (feature-implementation-plan §26).

Compare the rival contentions across a set of pleadings:

  1. Derive the disputed *issues* from the combined pleadings (one LLM call).
  2. Classify each pleading's *stance* on every issue (one call per document).
  3. Write an overall dispute *summary* (one call).

Total LLM calls = n_docs + 2, bounded by MAX_DOCS + 2. All analysis uses ONLY
the supplied document text (no external retrieval); a per-document failure is
isolated in that document's ``error`` and never aborts the run — the same
contract as :func:`src.review.engine.run_review`.
"""

from __future__ import annotations

import asyncio

from src.providers.base import LLMProvider, Message
# Reuse the review engine's battle-tested helpers (retry on transient LLM errors,
# tolerant JSON extraction, stable key slugs) rather than re-implementing them.
from src.review.engine import _complete_with_retry, _extract_json, slugify_key

MAX_ISSUES = 12
MAX_DOCS = 10

# Per-document text budget for the per-document stance call.
CLASSIFY_MAX_CHARS = 18_000
# Combined text budget for the single issue-extraction call (split across docs).
ISSUES_TOTAL_CHARS = 40_000
MIN_PER_DOC_CHARS = 3_000

DEFAULT_CONCURRENCY = 5

STANCES = ("admits", "denies", "partially_admits", "not_addressed")
_NOT_ADDRESSED = "not_addressed"


def _coerce_stance(value) -> str:
    """Map an arbitrary model output to one of the fixed STANCES."""
    s = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in STANCES:
        return s
    # tolerate near-misses the model sometimes emits
    if s in ("admit", "admitted", "agrees", "agree", "accepts", "accept", "concedes"):
        return "admits"
    if s in ("deny", "denied", "denies", "disputes", "dispute", "rejects", "reject", "contests"):
        return "denies"
    if s.startswith("partial") or s in ("partly_admits", "partly"):
        return "partially_admits"
    return _NOT_ADDRESSED


_ISSUES_SYSTEM = (
    "You are a litigation analyst. You are given the pleadings or written submissions filed by "
    "opposing parties in a single dispute. Identify the distinct DISPUTED ISSUES / points of "
    "contention that run across these pleadings — the matters on which the parties take a position "
    "(whether they agree or disagree). Use ONLY the provided text. "
    'Return ONLY a JSON object {"issues": [{"title": "...", "summary": "..."}, ...]}, most '
    "significant issue first. Each 'title' is a short noun phrase (3-8 words); each 'summary' "
    "states the issue neutrally in one sentence. Do not exceed the requested number of issues."
)


async def extract_issues(
    llm: LLMProvider,
    docs: list[tuple[str, str, str]],
    *,
    max_issues: int = MAX_ISSUES,
) -> list[dict]:
    """Derive the disputed issues from the combined pleadings.

    ``docs`` is a list of ``(doc_id, filename, text)``. Returns a list of
    ``{key, title, summary}`` with stable, unique keys, capped at ``max_issues``.
    """
    if not docs:
        return []

    per_doc = max(MIN_PER_DOC_CHARS, ISSUES_TOTAL_CHARS // len(docs))
    blocks = []
    for i, (_id, filename, text) in enumerate(docs, start=1):
        blocks.append(f'PLEADING {i} (filename: {filename}):\n"""\n{(text or "")[:per_doc]}\n"""')
    user = (
        "\n\n".join(blocks)
        + f"\n\nIdentify up to {max_issues} distinct disputed issues across these pleadings. "
        "Return the JSON object."
    )
    resp = await _complete_with_retry(
        llm,
        [Message(role="system", content=_ISSUES_SYSTEM), Message(role="user", content=user)],
        max_tokens=1500,
        temperature=0.0,
        json_mode=True,
    )
    parsed = _extract_json(resp.content)
    raw = parsed.get("issues") if isinstance(parsed, dict) else None

    out: list[dict] = []
    seen: set[str] = set()
    if isinstance(raw, list):
        for i, item in enumerate(raw[:max_issues]):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            summary = str(item.get("summary") or "").strip()
            key = slugify_key(title, i)
            # guarantee uniqueness so stances never collide across issues
            base, n = key, 2
            while key in seen:
                key = f"{base}_{n}"
                n += 1
            seen.add(key)
            out.append({"key": key, "title": title[:200], "summary": summary[:500]})
    return out


_CLASSIFY_SYSTEM = (
    "You are a litigation analyst. You are given ONE party's pleading and a list of disputed "
    "issues. Classify this pleading's stance on EACH issue using ONLY the provided pleading text. "
    "For each issue return an object with:\n"
    '  "stance": exactly one of "admits", "denies", "partially_admits", "not_addressed"\n'
    '  "text": a short quote or paraphrase (<=300 chars) of what THIS pleading says on the issue, '
    'or "" if it is silent.\n'
    "Definitions: 'admits' = this pleading accepts/agrees with the proposition; 'denies' = "
    "rejects/disputes it; 'partially_admits' = accepts in part and disputes in part; "
    "'not_addressed' = this pleading is silent on the issue.\n"
    'Return ONLY a JSON object mapping each issue key to its {"stance": ..., "text": ...}.'
)


async def classify_positions(
    llm: LLMProvider,
    filename: str,
    text: str,
    issues: list[dict],
    *,
    max_chars: int = CLASSIFY_MAX_CHARS,
) -> dict[str, dict]:
    """Classify one pleading's stance on each issue. Returns {issue_key: {stance, text}}."""
    if not issues:
        return {}
    doc_text = (text or "")[:max_chars]
    issue_lines = "\n".join(f'- "{it["key"]}": {it["title"]} — {it.get("summary", "")}' for it in issues)
    user = (
        f'PLEADING (filename: {filename}):\n"""\n{doc_text}\n"""\n\n'
        f"ISSUES (classify this pleading's stance on each, keyed exactly as shown):\n{issue_lines}\n\n"
        'Return ONLY a JSON object like {"<key>": {"stance": "...", "text": "..."}, ...} with one '
        "entry per issue key above."
    )
    resp = await _complete_with_retry(
        llm,
        [Message(role="system", content=_CLASSIFY_SYSTEM), Message(role="user", content=user)],
        max_tokens=2000,
        temperature=0.0,
        json_mode=True,
    )
    parsed = _extract_json(resp.content)

    stances: dict[str, dict] = {}
    for it in issues:
        key = it["key"]
        cell = parsed.get(key) if isinstance(parsed, dict) else None
        if isinstance(cell, dict):
            stances[key] = {
                "stance": _coerce_stance(cell.get("stance")),
                "text": str(cell.get("text") or "").strip()[:300],
            }
        else:
            # Non-object cell: the model returned a bare string, or omitted the key.
            # A bare string is at best a stance keyword, never a usable quotation, so
            # coerce the stance from it but leave `text` empty — rendering the keyword
            # (or a stray sentence) as if it were a quote from the pleading produces a
            # self-contradictory cell (e.g. "Not addressed" over text asserting a denial).
            stances[key] = {
                "stance": _coerce_stance(cell) if isinstance(cell, str) else _NOT_ADDRESSED,
                "text": "",
            }
    return stances


_SUMMARY_SYSTEM = (
    "You are a litigation analyst. Given the disputed issues and each party's stance on them, write "
    "a concise, neutral summary (2-4 sentences) of what is genuinely in dispute between the parties "
    "and where they agree. Do not invent facts beyond the stances provided. Return plain prose only."
)


async def _summarize(llm: LLMProvider, issues: list[dict], positions: list[dict]) -> str:
    """One-call narrative summary of the dispute. Returns '' on failure (non-fatal)."""
    if not issues:
        return ""
    lines = []
    for it in issues:
        row = [f"Issue: {it['title']}"]
        for pos in positions:
            cell = (pos.get("stances") or {}).get(it["key"], {})
            row.append(f"  {pos.get('filename', pos.get('document_id'))}: {cell.get('stance', _NOT_ADDRESSED)}")
        lines.append("\n".join(row))
    user = "STANCES BY ISSUE:\n" + "\n\n".join(lines) + "\n\nWrite the dispute summary."
    try:
        resp = await _complete_with_retry(
            llm,
            [Message(role="system", content=_SUMMARY_SYSTEM), Message(role="user", content=user)],
            max_tokens=500,
            temperature=0.2,
            json_mode=False,
        )
        return (resp.content or "").strip()
    except Exception:  # noqa: BLE001 — summary is a nicety; never fail the whole run for it
        return ""


async def run_contentions(
    llm: LLMProvider,
    docs: list[tuple[str, str, str]],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    max_issues: int = MAX_ISSUES,
) -> dict:
    """Run the full pipeline over ``docs`` (list of ``(doc_id, filename, text)``).

    Returns ``{issues, results, summary}`` where ``results`` is a list of
    ``{document_id, filename, stances, error}`` in the same order as ``docs``.
    """
    if not docs:
        return {"issues": [], "results": [], "summary": ""}

    issues = await extract_issues(llm, docs, max_issues=max_issues)
    if not issues:
        return {
            "issues": [],
            "results": [
                {"document_id": d[0], "filename": d[1], "stances": {}, "error": None} for d in docs
            ],
            "summary": "No distinct contentions could be identified across the selected pleadings.",
        }

    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(doc: tuple[str, str, str]) -> dict:
        doc_id, filename, text = doc
        async with sem:
            try:
                stances = await classify_positions(llm, filename, text, issues)
                return {"document_id": doc_id, "filename": filename, "stances": stances, "error": None}
            except Exception as exc:  # noqa: BLE001 — isolate one pleading's failure
                return {
                    "document_id": doc_id,
                    "filename": filename,
                    # keep the matrix rectangular even when a doc fails
                    "stances": {it["key"]: {"stance": _NOT_ADDRESSED, "text": ""} for it in issues},
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                }

    positions = await asyncio.gather(*(_one(d) for d in docs))
    summary = await _summarize(llm, issues, positions)
    return {"issues": issues, "results": list(positions), "summary": summary}
