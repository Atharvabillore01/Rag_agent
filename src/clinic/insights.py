"""Clinical AI insights from a doctor's typed visit notes (feature-implementation-plan §33 P3).

One bounded JSON-mode LLM call turns free-text notes into structured, decision-
support insights. This is NOT a diagnosis; the model is told to avoid inventing
facts and to work only from the notes. No audio, no transcription — notes are typed.
"""

from __future__ import annotations

from src.providers.base import LLMProvider, Message
from src.review.engine import _complete_with_retry, _extract_json

DEFAULT_MAX_CHARS = 8_000
_MAX_ITEMS = 20

EMPTY = {
    "summary": "",
    "symptoms": [],
    "possible_conditions": [],
    "recommended_follow_up": "",
    "red_flags": [],
}

_SYSTEM = (
    "You are a clinical documentation assistant. Given a doctor's free-text visit notes, "
    "extract concise, structured decision-support insights. Use ONLY the information in the notes "
    "— do not invent facts, and do not state a definitive diagnosis. "
    'Return ONLY a JSON object with these keys: "summary" (2-3 sentence plain-language summary), '
    '"symptoms" (array of strings), "possible_conditions" (array of strings — differential '
    'considerations, phrased tentatively), "recommended_follow_up" (string), "red_flags" (array of '
    "strings — anything urgent/concerning to escalate). Use empty arrays/strings where not applicable."
)


def _strlist(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip()[:200] for x in value if str(x).strip()][:_MAX_ITEMS]


async def generate_insights(llm: LLMProvider, notes: str, *, max_chars: int = DEFAULT_MAX_CHARS) -> dict:
    """Return structured insights for ``notes``. Never raises for a malformed model
    response — degrades to the EMPTY shape so a visit is always saved."""
    if not notes or not notes.strip():
        return dict(EMPTY)
    user = f"VISIT NOTES:\n\"\"\"\n{notes[:max_chars]}\n\"\"\"\n\nReturn the JSON object."
    try:
        resp = await _complete_with_retry(
            llm,
            [Message(role="system", content=_SYSTEM), Message(role="user", content=user)],
            max_tokens=1000, temperature=0.1, json_mode=True,
        )
    except Exception:  # noqa: BLE001 — insights are best-effort; the visit still saves
        return dict(EMPTY)
    parsed = _extract_json(resp.content)
    if not isinstance(parsed, dict):
        return dict(EMPTY)
    return {
        "summary": str(parsed.get("summary") or "").strip()[:2000],
        "symptoms": _strlist(parsed.get("symptoms")),
        "possible_conditions": _strlist(parsed.get("possible_conditions")),
        "recommended_follow_up": str(parsed.get("recommended_follow_up") or "").strip()[:1000],
        "red_flags": _strlist(parsed.get("red_flags")),
    }
