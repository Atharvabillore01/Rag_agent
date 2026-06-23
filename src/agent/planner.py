"""Query planner — decomposes complex queries into sub-questions (§4.1, §4.6)."""

import json
from dataclasses import dataclass, field

from src.agent.prompts import PLANNER_SYSTEM, PLANNER_USER, PROMPT_VERSION
from src.providers.base import LLMProvider, Message
from src.providers.factory import llm


@dataclass
class SubQuestion:
    id: str
    question: str
    target_documents: list[str] = field(default_factory=list)
    retrieval_strategy: str = "hybrid"
    required_evidence: str = ""


@dataclass
class PlanResult:
    needs_agentic_loop: bool
    subquestions: list[SubQuestion]
    stop_conditions: list[str]
    max_rounds: int
    prompt_version: str = PROMPT_VERSION


async def plan_query(
    query: str,
    doc_metadata: str,
    max_rounds: int = 3,
    provider: LLMProvider | None = None,
) -> PlanResult:
    """Decide whether agentic loop is needed and decompose if so."""
    provider = provider or llm()

    messages = [
        Message(role="system", content=PLANNER_SYSTEM),
        Message(
            role="user",
            content=PLANNER_USER.format(
                query=query,
                doc_metadata=doc_metadata,
                max_rounds=max_rounds,
            ),
        ),
    ]

    response = await provider.complete(messages, max_tokens=512, temperature=0.0, json_mode=True)

    try:
        data = json.loads(response.content)
        subquestions = [
            SubQuestion(
                id=sq.get("id", f"sq{i}"),
                question=sq.get("question", query),
                target_documents=sq.get("target_documents", []),
                retrieval_strategy=sq.get("retrieval_strategy", "hybrid"),
                required_evidence=sq.get("required_evidence", ""),
            )
            for i, sq in enumerate(data.get("subquestions", []))
        ]
        if not subquestions:
            subquestions = [SubQuestion(id="sq1", question=query)]

        return PlanResult(
            needs_agentic_loop=bool(data.get("needs_agentic_loop", True)),
            subquestions=subquestions,
            stop_conditions=data.get("stop_conditions", ["sufficient direct evidence found"]),
            max_rounds=int(data.get("max_rounds", max_rounds)),
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        # Fail safe — single sub-question, no agentic loop
        return PlanResult(
            needs_agentic_loop=False,
            subquestions=[SubQuestion(id="sq1", question=query)],
            stop_conditions=[""],
            max_rounds=1,
        )
