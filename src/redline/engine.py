"""Redline engine (feature-implementation-plan §8).

The factual diff between two documents is computed deterministically with
difflib — grounded, reproducible, free. The LLM is used ONLY to characterize
each real change and its consequence; it never invents the diff.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from src.providers.base import LLMProvider, Message
# Reuse the review engine's defensive JSON parse + transient-retry wrapper.
from src.review.engine import _complete_with_retry, _extract_json

MAX_CHANGES = 30
_SEG_MAX = 800  # cap each before/after segment sent to the LLM

_SYSTEM = (
    "You are a contract redline analyst. You are given the real, already-computed "
    "changes between a base and a revised version of a document. For each change, "
    "write a concise plain-English summary of WHAT changed, and a concise assessment "
    "of its legal/business CONSEQUENCE. Base everything only on the provided change "
    'text — do not invent changes. Return a JSON object of the form '
    '{"changes": [{"change": "...", "consequence": "..."}, ...]} with one entry per '
    "change, in the same order."
)


@dataclass
class Change:
    change_type: str  # insertion | deletion | modification
    before: str
    after: str


def _segment(text: str) -> list[str]:
    """Split text into comparable units (non-empty lines / paragraph fragments)."""
    segs: list[str] = []
    for para in re.split(r"\n\s*\n", text or ""):
        for line in para.split("\n"):
            s = line.strip()
            if s:
                segs.append(s)
    return segs


def compute_changes(
    base_text: str, revised_text: str, *, max_changes: int = MAX_CHANGES
) -> list[Change]:
    """Deterministic paragraph-level diff → typed changes (capped)."""
    base = _segment(base_text)
    rev = _segment(revised_text)
    sm = difflib.SequenceMatcher(a=base, b=rev, autojunk=False)
    tmap = {"replace": "modification", "delete": "deletion", "insert": "insertion"}
    out: list[Change] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        # difflib groups CONTIGUOUS changed lines into one opcode. For a clean
        # 1:1 replacement (same number of before/after lines) split it into
        # per-line modifications so each edited clause is its own row — much more
        # useful for a legal redline than one merged multi-clause block.
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                out.append(Change("modification", base[i1 + k].strip(), rev[j1 + k].strip()))
                if len(out) >= max_changes:
                    return out
        else:
            out.append(
                Change(
                    change_type=tmap[tag],
                    before=" ".join(base[i1:i2]).strip(),
                    after=" ".join(rev[j1:j2]).strip(),
                )
            )
            if len(out) >= max_changes:
                break
    return out


def _default_summary(c: Change) -> str:
    if c.change_type == "insertion":
        return f"Added: {c.after[:120]}"
    if c.change_type == "deletion":
        return f"Removed: {c.before[:120]}"
    return f"Changed “{c.before[:60]}” to “{c.after[:60]}”"


async def explain_changes(llm: LLMProvider, changes: list[Change]) -> list[dict]:
    """Batch all changes into one JSON call → rows of change_type/before/after/change/consequence."""
    if not changes:
        return []

    lines = []
    for i, c in enumerate(changes, 1):
        lines.append(
            f"{i}. type={c.change_type}\n"
            f"   BEFORE: {c.before[:_SEG_MAX] or '(none)'}\n"
            f"   AFTER: {c.after[:_SEG_MAX] or '(none)'}"
        )
    user = (
        "Changes between the base and revised document:\n\n"
        + "\n\n".join(lines)
        + f'\n\nReturn a JSON object {{"changes": [...]}} with exactly {len(changes)} '
        "entries in order, each {\"change\": \"...\", \"consequence\": \"...\"}."
    )
    messages = [Message(role="system", content=_SYSTEM), Message(role="user", content=user)]
    resp = await _complete_with_retry(llm, messages, max_tokens=2200, temperature=0.0, json_mode=True)

    parsed = _extract_json(resp.content)
    arr = parsed.get("changes") if isinstance(parsed, dict) else None
    if not isinstance(arr, list):
        arr = []

    rows: list[dict] = []
    for i, c in enumerate(changes):
        item = arr[i] if i < len(arr) and isinstance(arr[i], dict) else {}
        rows.append(
            {
                "change_type": c.change_type,
                "before": c.before,
                "after": c.after,
                "change": (str(item.get("change") or "").strip() or _default_summary(c)),
                "consequence": (str(item.get("consequence") or "").strip() or "Not assessed."),
            }
        )
    return rows


async def run_redline(
    llm: LLMProvider, base_text: str, revised_text: str, *, max_changes: int = MAX_CHANGES
) -> list[dict]:
    changes = compute_changes(base_text, revised_text, max_changes=max_changes)
    return await explain_changes(llm, changes)
