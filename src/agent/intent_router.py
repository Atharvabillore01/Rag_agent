"""Intent router — cheap model classifies query before any retrieval (§4.1, §5.1)."""

import json
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


@dataclass
class IntentResult:
    intent: str
    confidence: float
    clarifying_question: str | None
    routing_notes: str
    prompt_version: str = PROMPT_VERSION


async def classify_intent(message: str) -> IntentResult:
    """Classify user intent with the cheap router model."""
    llm = router_llm()

    messages = [
        Message(role="system", content=INTENT_ROUTER_SYSTEM),
        Message(
            role="user",
            content=INTENT_ROUTER_USER.format(message=message),
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
        # Fail safe — treat unparseable output as ambiguous
        return IntentResult(
            intent="ambiguous",
            confidence=0.0,
            clarifying_question=None,
            routing_notes="intent router returned non-JSON; defaulting to ambiguous",
        )
