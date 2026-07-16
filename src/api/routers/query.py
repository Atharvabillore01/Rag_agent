"""Query / agentic retrieval endpoints — SSE streaming (§4, §8.2)."""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.agent.loop import AgentContext, run_agent_loop
from src.api.auth import require_viewer
from src.api.deps import get_cache_dep, get_vector_store_dep
from src.config import get_settings
from src.db.models import User
from src.storage.cache import CacheClient
from src.storage.vector import VectorStore

router = APIRouter(prefix="/query", tags=["query"])
settings = get_settings()
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    collection_tags: list[str] | None = None
    client_request_id: str | None = None  # for mobile idempotency (§8.2)


def _sse_event(event_type: str, data: dict, seq: int) -> str:
    payload = {"event_type": event_type, "seq": seq, **data}
    return f"data: {json.dumps(payload)}\n\n"


async def _enforce_daily_quota(cache: CacheClient, current_user: User) -> None:
    """G8: enforce a per-tenant daily query quota (demo tenants get the stricter
    demo cap). Counts only real queries — cache hits are checked before this and
    served free. Raises 429 once the cap is exceeded."""
    if current_user.role.value == "demo":
        count = await cache.incr_demo_queries(current_user.tenant_id)
        limit = settings.rate_limit_demo_qpd
    else:
        count = await cache.incr_daily_queries(current_user.tenant_id)
        limit = settings.rate_limit_default_qpd
    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Daily query quota reached ({limit} queries). Resets in 24 hours.",
            headers={"Retry-After": "3600"},
        )


@router.post("/stream")
async def stream_query(
    body: QueryRequest,
    current_user: User = Depends(require_viewer),
    vector_store: VectorStore = Depends(get_vector_store_dep),
    cache: CacheClient = Depends(get_cache_dep),
):
    """
    SSE streaming query endpoint.

    Returns a stream of events: status → token_delta* → citation* → final_answer → done
    Each event includes a monotonic seq number for mobile replay (§8.2).
    """
    query_id = str(uuid.uuid4())

    # Check query cache for identical recent queries (§4.3)
    cached = await cache.get_query_cache(
        current_user.tenant_id, body.question, body.collection_tags
    )

    # G8: enforce the daily query quota on real (non-cached) queries only.
    if not cached:
        await _enforce_daily_quota(cache, current_user)

    context = AgentContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        collection_tags=body.collection_tags or current_user.collection_tags,
        is_demo=current_user.role.value == "demo",
    )

    async def event_generator():
        seq = 0
        try:
            if cached:
                yield _sse_event("status", {"message": "Returning cached answer"}, seq)
                seq += 1
                yield _sse_event("final_answer", cached, seq)
                seq += 1
                yield _sse_event("done", {}, seq)
                return

            async for agent_event in run_agent_loop(
                query=body.question,
                context=context,
                vector_store=vector_store,
            ):
                sse = _sse_event(agent_event.event_type, agent_event.payload, agent_event.seq)

                # Buffer for mobile reconnect replay (§8.2)
                await cache.push_stream_event(
                    current_user.tenant_id,
                    query_id,
                    {"event_type": agent_event.event_type, **agent_event.payload},
                    ttl=settings.stream_buffer_ttl_seconds,
                )

                yield sse

                # Cache the final answer
                if agent_event.event_type == "final_answer":
                    await cache.set_query_cache(
                        current_user.tenant_id,
                        body.question,
                        body.collection_tags,
                        agent_event.payload,
                        ttl=settings.query_cache_ttl_seconds,
                    )

        except Exception as exc:
            # G16: never stream raw internals to the client — log server-side,
            # return a generic message.
            logger.error("query stream failed for tenant=%s: %s", current_user.tenant_id, exc, exc_info=exc)
            yield _sse_event("error", {"message": "An internal error occurred while processing your query."}, 9999)
            yield _sse_event("done", {}, 10000)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Query-Id": query_id,
        },
    )


@router.get("/replay/{query_id}")
async def replay_query_stream(
    query_id: str,
    last_seq: int = 0,
    current_user: User = Depends(require_viewer),
    cache: CacheClient = Depends(get_cache_dep),
):
    """Replay buffered stream events for mobile reconnect (§8.2)."""
    events = await cache.get_stream_events(current_user.tenant_id, query_id, after_seq=last_seq)

    async def replay_generator():
        for i, event in enumerate(events):
            yield _sse_event(
                event.get("event_type", "status"), event, last_seq + i
            )

    return StreamingResponse(replay_generator(), media_type="text/event-stream")
