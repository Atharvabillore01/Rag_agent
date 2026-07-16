"""Agentic retrieval loop — orchestrates intent → plan → retrieve → verify → generate (§4.1)."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.generator import _parse_answer_and_citations, stream_answer
from src.agent.intent_router import IntentResult, classify_intent
from src.agent.planner import PlanResult, SubQuestion, plan_query
from src.agent.retriever import RetrievedChunk, hybrid_retrieve
from src.agent.verifier import VerifierResult, verify_retrieval
from src.config import get_settings
from src.db.models import AuditAction, AuditLog, Document, DocumentStatus, Tenant
from src.db.session import AsyncSessionLocal
from src.providers.base import LLMProvider
from src.providers.factory import get_tenant_llm
from src.storage.vector import VectorStore


@dataclass
class AgentEvent:
    """Streaming status event sent to the client (§8.2, §4.3)."""
    event_type: str   # status | citation | token_delta | final_answer | error | done
    seq: int
    payload: dict = field(default_factory=dict)


@dataclass
class AgentContext:
    tenant_id: str
    user_id: str
    collection_tags: list[str] | None
    is_demo: bool = False


async def _fetch_tenant_llm(db: AsyncSession, tenant_id: str) -> LLMProvider:
    """Return the LLM provider for this tenant, respecting per-tenant overrides."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    provider_override = tenant.llm_provider_override if tenant else None
    model_override = tenant.llm_model_override if tenant else None
    return get_tenant_llm(provider_override, model_override)


async def _fetch_doc_metadata(db: AsyncSession, tenant_id: str) -> tuple[str, dict[str, str]]:
    """Return (planner text, filename→uuid map) for ready documents."""
    settings = get_settings()
    result = await db.execute(
        select(Document.id, Document.filename, Document.file_type, Document.page_count)
        .where(
            Document.tenant_id == tenant_id,
            Document.status.in_([DocumentStatus.ready, DocumentStatus.ready_with_warnings]),
        )
        .limit(settings.agent_doc_metadata_limit)
    )
    rows = result.fetchall()
    if not rows:
        return "No documents are available.", {}
    lines = [
        f"{i+1}. {r[1]}  [{r[2].upper()}{f' · {r[3]} pages' if r[3] else ''}]"
        for i, r in enumerate(rows)
    ]
    # Index both bare filename and the "N. filename" form shown to the planner,
    # so planner output like "2. DPR- Telangana.pdf" resolves correctly.
    name_to_id = {}
    for i, r in enumerate(rows):
        name_to_id[r[1]] = r[0]
        name_to_id[f"{i + 1}. {r[1]}"] = r[0]
    return "\n".join(lines), name_to_id


async def run_agent_loop(
    query: str,
    context: AgentContext,
    vector_store: VectorStore,
) -> AsyncGenerator[AgentEvent, None]:
    """Full agentic loop as an async generator of AgentEvents.

    The DB session is scoped to the retrieval phase only and released before
    streaming starts — this prevents a connection from being held open for the
    entire duration of a token stream under concurrent load.
    """
    settings = get_settings()
    seq = 0

    def event(event_type: str, **payload) -> AgentEvent:
        nonlocal seq
        e = AgentEvent(event_type=event_type, seq=seq, payload=payload)
        seq += 1
        return e

    # ── 1. Intent classification (no DB) ──────────────────────────────────────
    yield event("status", message="Classifying intent...")
    intent_result: IntentResult = await classify_intent(query)

    if intent_result.intent == "greeting":
        yield event("final_answer", answer="Hello! How can I help you with your documents today?", citations=[])
        yield event("done")
        return

    if intent_result.intent == "out_of_scope":
        yield event("final_answer", answer="I can only answer questions about documents in your workspace. Could you rephrase your question?", citations=[])
        yield event("done")
        return

    if intent_result.intent == "ambiguous" and intent_result.clarifying_question:
        yield event("final_answer", answer=intent_result.clarifying_question, citations=[], needs_clarification=True)
        yield event("done")
        return

    if intent_result.intent == "system_meta":
        # Answer meta questions about available documents directly from Postgres —
        # no retrieval needed.
        async with AsyncSessionLocal() as db:
            doc_metadata, _ = await _fetch_doc_metadata(db, context.tenant_id)
        if doc_metadata == "No documents are available.":
            answer = "You have no documents uploaded yet. Use the Documents page to upload files."
        else:
            answer = f"Here are the documents available in your workspace:\n\n{doc_metadata}"
        yield event("final_answer", answer=answer, citations=[])
        yield event("done")
        return

    # ── 2-3. Plan + Retrieve (DB session — released before generation) ────────
    max_rounds = (
        settings.demo_max_retrieval_rounds if context.is_demo
        else settings.agent_max_retrieval_rounds
    )

    all_chunks: list[RetrievedChunk] = []
    tenant_provider: LLMProvider | None = None
    planner_summary = ""
    id_to_name: dict[str, str] = {}  # UUID → filename, passed to generator

    async with AsyncSessionLocal() as db:
        tenant_provider = await _fetch_tenant_llm(db, context.tenant_id)

        # Write audit log — cache hits never reach this code, so this is one
        # record per real agentic query, not per cache hit.
        db.add(AuditLog(
            tenant_id=context.tenant_id,
            user_id=context.user_id,
            action=AuditAction.document_query.value,
            log_metadata={"question": query[:500]},
        ))
        await db.commit()

        yield event("status", message="Planning retrieval strategy...")
        doc_metadata, name_to_id = await _fetch_doc_metadata(db, context.tenant_id)
        # Invert for the generator (bare filename entries don't start with a digit)
        id_to_name = {v: k for k, v in name_to_id.items() if not k[:1].isdigit()}
        plan: PlanResult = await plan_query(
            query=query,
            doc_metadata=doc_metadata,
            max_rounds=max_rounds,
            provider=tenant_provider,
        )

        # Resolve filenames → UUIDs in target_documents.
        # The planner LLM only sees filenames, so it returns filenames.
        # The retriever's _authorize_document_ids does a UUID lookup — filenames
        # never match, causing silent empty results.
        for subq in plan.subquestions:
            if subq.target_documents:
                subq.target_documents = [
                    name_to_id.get(td, td) for td in subq.target_documents
                ]

        if not plan.needs_agentic_loop:
            plan.subquestions = plan.subquestions[:1]
            plan.max_rounds = 1
        else:
            sq_lines = "\n".join(
                f"  {i+1}. {sq.question}"
                for i, sq in enumerate(plan.subquestions)
            )
            yield event("thinking", message=f"Breaking into {len(plan.subquestions)} sub-question(s):\n{sq_lines}")

        seen_chunk_ids: set[str] = set()
        verifier: VerifierResult | None = None

        subquestions = plan.subquestions or [SubQuestion(id="sq0", question=query)]
        total_rounds = min(len(subquestions), plan.max_rounds)

        for round_num, subq in enumerate(subquestions[:total_rounds], 1):
            if verifier and verifier.suggested_query_rewrites:
                retrieval_query = verifier.suggested_query_rewrites[0]
            else:
                retrieval_query = subq.question

            yield event("status", message=f"Searching documents (round {round_num}/{total_rounds}): {retrieval_query[:60]}...")

            round_chunks = await hybrid_retrieve(
                query=retrieval_query,
                tenant_id=context.tenant_id,
                vector_store=vector_store,
                db=db,
                top_k=settings.agent_retrieval_top_k,
                rerank_top_n=settings.agent_rerank_top_n,
                collection_tags=context.collection_tags,
                retrieval_strategy=subq.retrieval_strategy,
                document_ids=subq.target_documents or None,
            )

            for chunk in round_chunks:
                if chunk.chunk_id not in seen_chunk_ids:
                    seen_chunk_ids.add(chunk.chunk_id)
                    all_chunks.append(chunk)

            yield event("status", message=f"Verifying relevance of {len(all_chunks)} unique chunks...")
            verifier = await verify_retrieval(
                query=query,
                chunks=all_chunks,
                current_round=round_num,
                max_rounds=total_rounds,
                provider=tenant_provider,
            )

            if verifier.sufficient or not verifier.should_retry:
                break

            if verifier.missing_evidence:
                yield event("thinking", message=f"Still missing: {'; '.join(verifier.missing_evidence[:3])}")

            if verifier.suggested_query_rewrites:
                yield event("status", message=f"Reformulating: {verifier.suggested_query_rewrites[0][:80]}...")

        planner_summary = f"Planned {len(plan.subquestions)} sub-question(s). Agentic loop: {plan.needs_agentic_loop}."

    # ── DB session released here ───────────────────────────────────────────────
    # Everything below (token streaming) runs without holding a DB connection.

    # ── 4. Streaming generation ────────────────────────────────────────────────
    if not all_chunks:
        yield event(
            "final_answer",
            answer="I couldn't find relevant information in your documents to answer this question. Please try rephrasing or check which documents are available.",
            citations=[],
        )
        yield event("done")
        return

    yield event("status", message="Generating answer...")

    full_parts: list[str] = []
    async for token in stream_answer(query, all_chunks, planner_summary, provider=tenant_provider, doc_names=id_to_name):
        full_parts.append(token)
        yield event("token_delta", token=token)

    full_answer = "".join(full_parts)
    answer_text, citations = _parse_answer_and_citations(full_answer, all_chunks, id_to_name)

    def _citation_payload(c) -> dict:
        return {
            "number": c.number,
            "document_id": c.document_id,
            "chunk_id": c.chunk_id,
            "page_number": c.page_number,
            "section_heading": c.section_heading,
            "filename": c.filename,
            "snippet": c.snippet,
        }

    for citation in citations:
        yield event("citation", **_citation_payload(citation))

    yield event("final_answer", answer=answer_text, citations=[_citation_payload(c) for c in citations])
    yield event("done")
