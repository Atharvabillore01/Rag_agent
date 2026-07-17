"""Contract Playbook Review engine (feature-implementation-plan §30).

Assess a contract against a playbook of standard positions: for each clause type,
does the contract meet the standard, deviate from it, or omit it — and at what
risk. One bounded JSON-mode LLM call over the (labelled, truncated) contract text;
uses ONLY the supplied documents.
"""

from __future__ import annotations

import json
import re

from src.providers.base import LLMProvider, Message
from src.review.engine import _complete_with_retry, _extract_json, slugify_key


def _extract_list(text: str) -> list:
    """Best-effort parse of a top-level JSON array from an LLM response (handles a
    bare array or one wrapped in ```json fences). Returns [] if none is found."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    try:
        obj = json.loads(t)
        if isinstance(obj, list):
            return obj
    except Exception:
        m = re.search(r"\[.*\]", t, re.DOTALL)
        if m:
            try:
                obj = json.loads(m.group(0))
                return obj if isinstance(obj, list) else []
            except Exception:
                return []
    return []

MAX_DOCS = 10
MAX_CLAUSES = 40
DEFAULT_MAX_CHARS = 40_000
MIN_PER_DOC_CHARS = 3_000

STATUSES = ("meets", "deviates", "missing")
RISKS = ("none", "low", "medium", "high")

# Built-in playbook — plain data so onboarding a clause type is a one-line edit.
DEFAULT_PLAYBOOK: list[dict] = [
    {"clause_type": "Limitation of Liability",
     "standard": "Liability is capped (e.g. at fees paid in the preceding 12 months) and excludes indirect, incidental and consequential damages."},
    {"clause_type": "Indemnity",
     "standard": "Indemnities are mutual, limited to third-party claims, and subject to the liability cap where applicable."},
    {"clause_type": "Termination",
     "standard": "Either party may terminate for material breach with a cure period (e.g. 30 days); termination for convenience only on reasonable notice."},
    {"clause_type": "Confidentiality",
     "standard": "Mutual confidentiality with standard exclusions and a defined survival period (3-5 years)."},
    {"clause_type": "Governing Law & Jurisdiction",
     "standard": "Governed by Indian law with a specified seat whose courts have exclusive jurisdiction."},
    {"clause_type": "Payment Terms",
     "standard": "Payment within a defined period (e.g. 30 days) with interest on late payment."},
    {"clause_type": "Force Majeure",
     "standard": "Standard force majeure with prompt notice and a termination right if the event continues beyond a set period."},
    {"clause_type": "Dispute Resolution",
     "standard": "Disputes resolved by arbitration (seat, rules and number of arbitrators specified) with escalation before litigation."},
    {"clause_type": "Assignment",
     "standard": "No assignment without prior written consent, except to affiliates or on a change of control."},
    {"clause_type": "Intellectual Property",
     "standard": "Pre-existing IP remains each party's; ownership of deliverables / foreground IP is clearly allocated."},
]


def _coerce(value, allowed: tuple[str, ...], default: str) -> str:
    s = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return s if s in allowed else default


def merge_playbook(custom: list[dict] | None) -> list[dict]:
    """Merge caller-supplied clauses over the defaults, then append any new clause
    types. Returns the effective playbook (capped, well-formed).

    Matching is keyed by the clause-type *slug* (case/whitespace-insensitive) — the
    same slug run_playbook_review uses to pair model rows to clauses. This ensures
    a custom "indemnity" overrides the default "Indemnity" instead of producing a
    duplicate row that would later collide on the shared slug.
    """
    by_key: dict[str, dict] = {}
    order: list[str] = []
    for entry in DEFAULT_PLAYBOOK:
        key = slugify_key(entry["clause_type"], 0)
        by_key[key] = dict(entry)
        order.append(key)
    for entry in custom or []:
        if not isinstance(entry, dict):
            continue
        ct = str(entry.get("clause_type") or "").strip()
        std = str(entry.get("standard") or "").strip()
        if not ct or not std:
            continue
        key = slugify_key(ct, 0)
        if key not in by_key:
            order.append(key)
        by_key[key] = {"clause_type": ct[:120], "standard": std[:1000]}
    return [by_key[k] for k in order][:MAX_CLAUSES]


_SYSTEM = (
    "You are a contract review assistant. You are given a contract and a PLAYBOOK of standard "
    "positions. For EACH playbook clause type, assess the contract using ONLY the provided text:\n"
    '  "status": "meets" (the contract matches the standard), "deviates" (present but weaker/'
    'different), or "missing" (the contract has no such clause);\n'
    '  "risk": "none", "low", "medium", or "high" — the risk to our client of the deviation/absence;\n'
    '  "document_position": a short summary of what the contract actually says (or "" if missing);\n'
    '  "recommendation": a short suggested fix (or "" if it already meets the standard).\n'
    'Return ONLY a JSON object {"assessments": [{"clause_type": "...", "status": "...", "risk": "...", '
    '"document_position": "...", "recommendation": "..."}, ...]} with one entry per playbook clause '
    "type, keyed by the exact clause_type given."
)


async def run_playbook_review(
    llm: LLMProvider,
    docs: list[tuple[str, str, str]],
    playbook: list[dict],
) -> dict:
    """Return ``{playbook, results, summary}``.

    ``results`` has one assessment per playbook clause type (rectangular), each
    ``{clause_type, standard, status, risk, document_position, recommendation}``.
    Missing/omitted clauses default to status="missing", risk="medium" so the row
    is never silently dropped.
    """
    if not playbook:
        return {"playbook": [], "results": [], "summary": {"by_status": {}, "by_risk": {}}}

    # Empty selection -> every clause is "missing".
    if not docs:
        results = [
            {"clause_type": p["clause_type"], "standard": p["standard"], "status": "missing",
             "risk": "medium", "document_position": "", "recommendation": ""}
            for p in playbook
        ]
        return {"playbook": playbook, "results": results, "summary": _summarize(results)}

    per_doc = max(MIN_PER_DOC_CHARS, DEFAULT_MAX_CHARS // len(docs))
    blocks = [
        f'CONTRACT DOCUMENT {i} (filename: {fn}):\n"""\n{(text or "")[:per_doc]}\n"""'
        for i, (_id, fn, text) in enumerate(docs, start=1)
    ]
    pb_lines = "\n".join(f'- "{p["clause_type"]}": {p["standard"]}' for p in playbook)
    user = (
        "\n\n".join(blocks)
        + f"\n\nPLAYBOOK (assess each clause type):\n{pb_lines}\n\nReturn the JSON object."
    )
    resp = await _complete_with_retry(
        llm,
        [Message(role="system", content=_SYSTEM), Message(role="user", content=user)],
        max_tokens=3000,
        temperature=0.0,
        json_mode=True,
    )
    parsed = _extract_json(resp.content)
    raw = parsed.get("assessments") if isinstance(parsed, dict) else None
    if not isinstance(raw, list):
        # tolerate a model that returns a bare top-level JSON array of assessments
        raw = _extract_list(resp.content)
    # index model output by a slug of clause_type for tolerant matching
    by_slug: dict[str, dict] = {}
    if isinstance(raw, list):
        for a in raw:
            if isinstance(a, dict) and a.get("clause_type"):
                by_slug[slugify_key(str(a["clause_type"]), 0)] = a

    results = []
    for p in playbook:
        a = by_slug.get(slugify_key(p["clause_type"], 0)) or {}
        status = _coerce(a.get("status"), STATUSES, "missing")
        # Risk default is STATUS-aware, not presence-aware: a matched row that omits
        # a valid risk must NOT default to "none" for a deviates/missing clause (that
        # would hide the very risk this tool exists to surface).
        risk = _coerce(a.get("risk"), RISKS, "none" if status == "meets" else "medium")
        results.append({
            "clause_type": p["clause_type"],
            "standard": p["standard"],
            "status": status,
            "risk": risk,
            "document_position": str(a.get("document_position") or "").strip()[:800],
            "recommendation": str(a.get("recommendation") or "").strip()[:800],
        })
    return {"playbook": playbook, "results": results, "summary": _summarize(results)}


def _summarize(results: list[dict]) -> dict:
    by_status: dict[str, int] = {}
    by_risk: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_risk[r["risk"]] = by_risk.get(r["risk"], 0) + 1
    return {"by_status": by_status, "by_risk": by_risk}
