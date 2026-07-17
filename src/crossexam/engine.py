"""Cross-Examination question generator (feature-implementation-plan §29).

From witness statements / affidavits / pleadings, produce an examination plan:
questions grouped by theme, each with its objective, the source basis it targets,
and a type. One bounded JSON-mode LLM call over the (labelled, truncated) source
text; uses ONLY the supplied documents (no external retrieval).
"""

from __future__ import annotations

from src.providers.base import LLMProvider, Message
from src.review.engine import _complete_with_retry, _extract_json

MAX_DOCS = 10
MAX_TOPICS = 15
MAX_QUESTIONS_PER_TOPIC = 20
DEFAULT_MAX_CHARS = 40_000
MIN_PER_DOC_CHARS = 3_000

# Fixed question-type vocabulary (coerced from model output).
TYPES = ("foundation", "contradiction", "impeachment", "admission")
_DEFAULT_TYPE = "foundation"


def _coerce_type(value) -> str:
    s = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if s in TYPES:
        return s
    if s in ("credibility", "impeach", "prior_inconsistent", "inconsistency"):
        return "impeachment"
    if s in ("contradict", "contradictory", "inconsistent"):
        return "contradiction"
    if s in ("admit", "admits", "concession", "concede"):
        return "admission"
    if s in ("background", "foundational", "setup"):
        return "foundation"
    return _DEFAULT_TYPE


_SYSTEM = (
    "You are an experienced trial lawyer preparing to cross-examine a witness. You are given that "
    "witness's statement / affidavit / pleading. Produce a focused cross-examination plan using ONLY "
    "the provided text — do not invent facts. Group questions by THEME. For each question give:\n"
    '  "question": a single, leading cross-examination question (one fact per question);\n'
    '  "objective": what the question is meant to establish or undermine;\n'
    '  "basis": the specific statement/paragraph/quote in the source it targets (or "" if general);\n'
    '  "type": one of "foundation", "contradiction", "impeachment", "admission".\n'
    'Return ONLY a JSON object {"topics": [{"topic": "...", "questions": [{...}, ...]}, ...]} and '
    "nothing else."
)


async def generate_cross_exam(
    llm: LLMProvider,
    docs: list[tuple[str, str, str]],
    instruction: str | None = None,
    *,
    max_topics: int = MAX_TOPICS,
) -> list[dict]:
    """Return a list of ``{topic, questions:[{question, objective, basis, type}]}``.

    ``docs`` is ``[(doc_id, filename, text)]``. ``instruction`` is an optional case
    theory that steers the questions. Returns [] if the model yields nothing usable.
    """
    if not docs:
        return []

    per_doc = max(MIN_PER_DOC_CHARS, DEFAULT_MAX_CHARS // len(docs))
    blocks = [
        f'SOURCE {i} (filename: {fn}):\n"""\n{(text or "")[:per_doc]}\n"""'
        for i, (_id, fn, text) in enumerate(docs, start=1)
    ]
    theory = f"\n\nCASE THEORY / FOCUS (steer the questions toward this):\n{instruction.strip()}" if instruction and instruction.strip() else ""
    user = (
        "\n\n".join(blocks)
        + theory
        + f"\n\nProduce up to {max_topics} themed groups of cross-examination questions. Return the JSON object."
    )
    resp = await _complete_with_retry(
        llm,
        [Message(role="system", content=_SYSTEM), Message(role="user", content=user)],
        max_tokens=3000,
        temperature=0.2,
        json_mode=True,
    )
    parsed = _extract_json(resp.content)
    raw_topics = parsed.get("topics") if isinstance(parsed, dict) else None
    if not isinstance(raw_topics, list):
        return []

    topics: list[dict] = []
    for t in raw_topics[:max_topics]:
        if not isinstance(t, dict):
            continue
        name = str(t.get("topic") or "").strip()
        raw_qs = t.get("questions")
        if not name or not isinstance(raw_qs, list):
            continue
        questions = []
        for q in raw_qs[:MAX_QUESTIONS_PER_TOPIC]:
            if not isinstance(q, dict):
                continue
            qtext = str(q.get("question") or "").strip()
            if not qtext:
                continue
            questions.append({
                "question": qtext[:1000],
                "objective": str(q.get("objective") or "").strip()[:500],
                "basis": str(q.get("basis") or "").strip()[:500],
                "type": _coerce_type(q.get("type")),
            })
        if questions:
            topics.append({"topic": name[:200], "questions": questions})
    return topics
