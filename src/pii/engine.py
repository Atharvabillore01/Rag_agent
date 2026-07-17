"""Sensitive-data (PII) detector + redactor (feature-implementation-plan §28).

Deterministic, checksum-hardened detection of sensitive identifiers, plus an
optional LLM pass for person names / addresses. Privacy by design: callers persist
only the *masked* value and a masked in-context snippet — never the raw value.

Detectors (regex + validation):
  * aadhaar      — 12 digits, Verhoeff checksum (kills the huge false-positive rate
                   of matching any 12-digit run)
  * pan          — ABCDE1234F
  * gstin        — 15-char GST identifier (contains a PAN; detected before PAN so
                   the longer match wins in de-duplication)
  * ifsc         — bank branch code AAAA0BBBBBB
  * credit_card  — 13-19 digits, Luhn checksum
  * email        — RFC-ish
  * phone_in     — Indian mobile (+91 optional), leading 6-9
"""

from __future__ import annotations

import asyncio
import re

from src.providers.base import LLMProvider, Message
from src.review.engine import _complete_with_retry, _extract_json

# ── Checksums ───────────────────────────────────────────────────────────────

# Verhoeff tables (Aadhaar uses the Verhoeff algorithm as its check digit).
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def _verhoeff_valid(number: str) -> bool:
    """True if the all-digit string passes the Verhoeff checksum (Aadhaar)."""
    if not number.isdigit():
        return False
    c = 0
    for i, ch in enumerate(reversed(number)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def _luhn_valid(number: str) -> bool:
    """True if the all-digit string passes the Luhn checksum (credit cards)."""
    if not number.isdigit():
        return False
    total, alt = 0, False
    for ch in reversed(number):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


# ── Detectors ───────────────────────────────────────────────────────────────

# Email: bounded, NON-overlapping domain grammar (label chars never include the
# separating dot) so there is no ambiguous split point — this avoids the O(n^2)
# catastrophic backtracking of a `[...\.]+\.[...]` pattern on adversarial text.
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9\-]{0,63}\.)+[A-Za-z]{2,24}\b"
)
_PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]\b")
_IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
# Aadhaar: 3×4 digits with up to two spaces/hyphens between groups (PDF text
# extraction often yields "1234  5678  9012" or "1234-5678-9012").
_AADHAAR_RE = re.compile(r"\b\d{4}[ \-]{0,2}\d{4}[ \-]{0,2}\d{4}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\-\s]?)?[6-9]\d{9}(?!\d)")
# Card: 13-19 digits, must start AND end on a digit so a trailing space/hyphen is
# never swallowed into the match (which would merge the redaction with next word).
_CARD_RE = re.compile(r"(?<!\d)\d(?:[ \-]?\d){12,18}(?!\d)")

TYPES = ("aadhaar", "pan", "gstin", "ifsc", "credit_card", "email", "phone_in")


def mask_value(value: str, kind: str) -> str:
    """Return a redacted rendering that reveals only a few edge characters."""
    if kind == "email":
        local, _, domain = value.partition("@")
        head = local[0] if local else ""
        dot = domain.rfind(".")
        if dot > 0:
            name, tld = domain[:dot], domain[dot:]
            dhead = name[0] if name else ""
            domain_masked = f"{dhead}{'*' * max(2, len(name) - 1)}{tld}"
        else:
            domain_masked = "*" * max(3, len(domain))
        return f"{head}{'*' * max(3, len(local) - 1)}@{domain_masked}"
    digits = [c for c in value if c.isalnum()]
    n = len(digits)
    # Aadhaar: reveal only the last 4 (aligns with UIDAI masking norms).
    if kind == "aadhaar" and n >= 4:
        return "*" * (n - 4) + "".join(digits[-4:])
    if n <= 4:
        return (digits[0] if digits else "") + "*" * max(1, n - 1)
    return "".join(digits[:2] + ["*"] * (n - 4) + digits[-2:])


def _window(masked_text: str, start: int, length: int, width: int = 30) -> str:
    """A context window taken from ALREADY-masked text, so every sensitive value
    inside it (not just the focal one) is masked — no raw PII can leak via a
    neighbouring match's context."""
    lo = max(0, start - width)
    hi = min(len(masked_text), start + length + width)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(masked_text) else ""
    return f"{prefix}{masked_text[lo:hi]}{suffix}".replace("\n", " ").strip()


def _raw_matches(text: str) -> list[dict]:
    """All candidate matches with raw value + span, checksum-validated. Internal —
    the raw ``value`` is used only for de-dup and redaction, never persisted."""
    out: list[dict] = []

    def add(kind, m, value=None):
        out.append({"type": kind, "value": value if value is not None else m.group(0),
                    "start": m.start(), "end": m.end()})

    for m in _GSTIN_RE.finditer(text):
        add("gstin", m)
    for m in _PAN_RE.finditer(text):
        add("pan", m)
    for m in _IFSC_RE.finditer(text):
        add("ifsc", m)
    for m in _AADHAAR_RE.finditer(text):
        digits = re.sub(r"[ \-]", "", m.group(0))
        if len(digits) == 12 and _verhoeff_valid(digits):
            add("aadhaar", m, value=m.group(0))
    for m in _CARD_RE.finditer(text):
        digits = re.sub(r"[ \-]", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_valid(digits):
            add("credit_card", m, value=m.group(0))
    for m in _EMAIL_RE.finditer(text):
        add("email", m)
    for m in _PHONE_RE.finditer(text):
        add("phone_in", m)
    return out


def _dedupe(matches: list[dict]) -> list[dict]:
    """Longest-match-wins: drop any match whose span is contained in another
    (e.g. the PAN inside a GSTIN, or a phone inside a card)."""
    ordered = sorted(matches, key=lambda x: (x["start"], -(x["end"] - x["start"])))
    kept: list[dict] = []
    for m in ordered:
        if any(k["start"] <= m["start"] and m["end"] <= k["end"] and k is not m for k in kept):
            continue
        # also drop if it overlaps a longer already-kept span
        if any(not (m["end"] <= k["start"] or m["start"] >= k["end"]) for k in kept):
            continue
        kept.append(m)
    return kept


def scan_text(text: str) -> list[dict]:
    """Detect sensitive values in ``text``.

    Returns findings ``{type, value, masked, start, end, snippet}`` sorted by
    position. ``value`` (raw) is included for the caller that redacts; API/storage
    layers must strip it and keep only ``masked``/``snippet``.
    """
    if not text:
        return []
    matches = sorted(_dedupe(_raw_matches(text)), key=lambda x: x["start"])
    if not matches:
        return []

    # Build a fully-masked copy of the text once, recording where each match lands
    # in it, so every snippet is drawn from text where ALL detected values (not
    # just the focal one) are already masked. This is what keeps raw PII out of
    # snippets that happen to sit next to another identifier.
    parts: list[str] = []
    masked_starts: list[int] = []
    pos = 0
    cur = 0
    prepared: list[tuple[str, str]] = []  # (mask, ) paired with match below
    for m in matches:
        parts.append(text[pos:m["start"]])
        cur += m["start"] - pos
        mask = mask_value(m["value"], m["type"])
        masked_starts.append(cur)
        prepared.append(mask)
        parts.append(mask)
        cur += len(mask)
        pos = m["end"]
    parts.append(text[pos:])
    masked_text = "".join(parts)

    findings = []
    for m, mask, mstart in zip(matches, prepared, masked_starts):
        findings.append({
            "type": m["type"],
            "value": m["value"],            # raw — for redaction only; never persisted
            "masked": mask,
            "start": m["start"],            # offsets into the ORIGINAL text (for redact_text)
            "end": m["end"],
            "snippet": _window(masked_text, mstart, len(mask)),
        })
    return findings


def redact_text(text: str) -> tuple[str, int]:
    """Return ``(redacted_text, count)`` with every detected value replaced by
    ``[REDACTED <TYPE>]``. Rebuilds the string in a SINGLE pass over sorted spans
    (O(n)) rather than one full-string rebuild per finding (which was O(n×findings))."""
    findings = scan_text(text)
    if not findings:
        return text, 0
    out: list[str] = []
    pos = 0
    for f in sorted(findings, key=lambda x: x["start"]):
        out.append(text[pos: f["start"]])
        out.append(f"[REDACTED {f['type'].upper()}]")
        pos = f["end"]
    out.append(text[pos:])
    return "".join(out), len(findings)


def public_findings(findings: list[dict]) -> list[dict]:
    """Strip raw value/offsets — the persistable, PII-free view of findings."""
    return [{"type": f["type"], "masked": f["masked"], "snippet": f["snippet"]} for f in findings]


# ── Optional LLM pass: person names / addresses ──────────────────────────────

_LLM_SYSTEM = (
    "You extract personal identifiers from the text: person names and postal addresses. "
    "Use ONLY the provided text. Return ONLY a JSON object "
    '{"items":[{"type":"person"|"address","value":"..."}, ...]} and nothing else. '
    "Do not include emails, phone numbers, or ID numbers (those are handled separately)."
)


async def llm_scan_text(llm: LLMProvider, text: str, *, max_chars: int = 12_000) -> list[dict]:
    """LLM pass for names/addresses. Returns public findings (no raw value stored
    beyond the mask). Best-effort: returns [] on any failure."""
    if not text.strip():
        return []
    try:
        resp = await _complete_with_retry(
            llm,
            [Message(role="system", content=_LLM_SYSTEM),
             Message(role="user", content=text[:max_chars] + "\n\nReturn the JSON.")],
            max_tokens=1200, temperature=0.0, json_mode=True,
        )
        parsed = _extract_json(resp.content)
        items = parsed.get("items") if isinstance(parsed, dict) else None
        out = []
        for it in (items or [])[:100]:
            if not isinstance(it, dict):
                continue
            kind = it.get("type")
            val = str(it.get("value") or "").strip()
            if kind in ("person", "address") and val:
                out.append({"type": kind, "masked": mask_value(val, kind), "snippet": ""})
        return out
    except Exception:  # noqa: BLE001
        return []


# ── Aggregate scan over documents ────────────────────────────────────────────

MAX_DOCS = 25
MAX_FINDINGS_PER_DOC = 500
# Hard cap on characters scanned per document. Bounds CPU on adversarial/huge
# inputs regardless of finding count (a doc with no detectable PII still costs
# one pass per regex over its text). ~1M chars ≈ a large filing.
MAX_SCAN_CHARS_PER_DOC = 1_000_000
_LLM_JOIN_CHARS = 12_000


async def run_scan(chunks: list[dict], *, llm: LLMProvider | None = None) -> dict:
    """Scan page-attributed ``chunks`` (from load_document_chunks) for sensitive data.

    ``chunks`` items are ``{document_id, filename, chunk_index, page_number, text}``.
    Returns ``{results, summary}`` where ``results`` is one entry per document
    ``{document_id, filename, findings, counts}`` with **only masked** findings
    (``{type, masked, snippet, page}``), and ``summary`` has overall counts.
    Never returns raw PII values.

    The per-chunk regex scan is CPU-bound; it is offloaded to a worker thread and
    bounded to ``MAX_SCAN_CHARS_PER_DOC`` per document so a huge or adversarial
    document cannot block the event loop or run unbounded.
    """
    by_doc: dict[str, dict] = {}
    order: list[str] = []
    scanned_chars: dict[str, int] = {}
    for ch in chunks:
        did = ch["document_id"]
        if did not in by_doc:
            by_doc[did] = {
                "document_id": did,
                "filename": ch.get("filename"),
                "findings": [],
                "counts": {},
            }
            order.append(did)
            scanned_chars[did] = 0
        entry = by_doc[did]
        if len(entry["findings"]) >= MAX_FINDINGS_PER_DOC:
            continue
        budget = MAX_SCAN_CHARS_PER_DOC - scanned_chars[did]
        if budget <= 0:
            continue
        text = (ch.get("text") or "")[:budget]
        scanned_chars[did] += len(text)
        for f in await asyncio.to_thread(scan_text, text):
            if len(entry["findings"]) >= MAX_FINDINGS_PER_DOC:
                break
            entry["findings"].append({
                "type": f["type"], "masked": f["masked"],
                "snippet": f["snippet"], "page": ch.get("page_number"),
            })
            entry["counts"][f["type"]] = entry["counts"].get(f["type"], 0) + 1

    # Optional LLM pass for names/addresses, over the joined text per document
    # (capped at _LLM_JOIN_CHARS so we never materialize an unbounded string).
    if llm is not None:
        joined: dict[str, str] = {}
        for ch in chunks:
            did = ch["document_id"]
            cur = joined.get(did, "")
            if len(cur) < _LLM_JOIN_CHARS:
                joined[did] = (cur + "\n" + (ch.get("text") or ""))[:_LLM_JOIN_CHARS]
        for did in order:
            entry = by_doc[did]
            if len(entry["findings"]) >= MAX_FINDINGS_PER_DOC:
                continue
            for f in await llm_scan_text(llm, joined.get(did, "")):
                if len(entry["findings"]) >= MAX_FINDINGS_PER_DOC:
                    break
                entry["findings"].append({**f, "page": None})
                entry["counts"][f["type"]] = entry["counts"].get(f["type"], 0) + 1

    summary: dict[str, int] = {}
    for did in order:
        for t, n in by_doc[did]["counts"].items():
            summary[t] = summary.get(t, 0) + n
    return {
        "results": [by_doc[d] for d in order],
        "summary": {"counts": summary, "total": sum(summary.values())},
    }
