"""Intent router — cheap model classifies query before any retrieval (§4.1, §5.1)."""

import json
import re
from dataclasses import dataclass

from src.agent.prompts import INTENT_ROUTER_SYSTEM, INTENT_ROUTER_USER, PROMPT_VERSION
from src.providers.base import Message
from src.providers.factory import router_llm


VALID_INTENTS = {
    "greeting",
    "system_meta",
    "document_question",
    "out_of_scope",
    "ambiguous",
}

# Fast-path patterns — skip the LLM call for high-confidence trivial cases
_GREETING_RE = re.compile(
    r"^(hi|hello|hey|greetings?|good\s+(morning|afternoon|evening|day)|"
    r"thanks?|thank\s+you|ty|ok|okay|sure|np|no\s+problem|great|perfect|bye|goodbye)\W*$",
    re.IGNORECASE,
)
# "which document mentions Karnataka" — content search, NOT system_meta.
# Must be checked BEFORE _SYSTEM_META_RE to take priority.
_DOC_CONTENT_SEARCH_RE = re.compile(
    r"\b(which|what)\s+(document|doc|file|pdf)\b.{0,80}"
    r"\b(mention|say|said|says|talk|talked|talks|discuss|about|contain|cover|state|refer|describe|include)\b",
    re.IGNORECASE,
)

_SYSTEM_META_RE = re.compile(
    r"(what|which|list|show|how\s+many|any|do\s+i\s+have|are\s+there|available|uploaded?)\b"
    r".{0,40}\b(document|doc|file|upload|pdf|attachment|report)s?\b"
    r"|\b(document|doc|file|pdf)s?\b.{0,30}\b(available|uploaded?|exist|loaded|added|there)\b"
    r"|\bwhat\s+(can\s+you|do\s+you)\s+(access|see|know\s+about|have)\b",
    re.IGNORECASE,
)


@dataclass
class IntentResult:
    intent: str
    confidence: float
    clarifying_question: str | None
    routing_notes: str
    prompt_version: str = PROMPT_VERSION


async def classify_intent(message: str) -> IntentResult:
    """Classify user intent with the cheap router model."""
    stripped = message.strip()

    # Fast path — skip Groq call for obvious cases (~1-2s saved)
    if _GREETING_RE.match(stripped):
        return IntentResult(
            intent="greeting",
            confidence=0.97,
            clarifying_question=None,
            routing_notes="fast-path: regex greeting",
        )
    # Must come before _SYSTEM_META_RE: "which document mentions X" is a content
    # search even though it starts with "which document".
    if _DOC_CONTENT_SEARCH_RE.search(stripped):
        return IntentResult(
            intent="document_question",
            confidence=0.95,
            clarifying_question=None,
            routing_notes="fast-path: regex doc content search",
        )
    if _SYSTEM_META_RE.search(stripped):
        return IntentResult(
            intent="system_meta",
            confidence=0.93,
            clarifying_question=None,
            routing_notes="fast-path: regex system_meta",
        )

    llm = router_llm()
    messages = [
        Message(role="system", content=INTENT_ROUTER_SYSTEM),
        Message(
            role="user",
            content=INTENT_ROUTER_USER.format(message=stripped),
        ),
    ]

    response = await llm.complete(messages, max_tokens=256, temperature=0.0, json_mode=True)

    try:
        data = json.loads(response.content)
        intent = data.get("intent", "ambiguous")
        if intent not in VALID_INTENTS:
            intent = "ambiguous"
        return IntentResult(
            intent=intent,
            confidence=float(data.get("confidence", 0.5)),
            clarifying_question=data.get("clarifying_question"),
            routing_notes=data.get("routing_notes", ""),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return IntentResult(
            intent="ambiguous",
            confidence=0.0,
            clarifying_question=None,
            routing_notes="intent router returned non-JSON; defaulting to ambiguous",
        )
