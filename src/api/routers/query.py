"""Query / agentic retrieval endpoints — SSE streaming (§4, §8.2)."""

import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.loop import AgentContext, run_agent_loop
from src.api.auth import require_viewer
from src.api.deps import get_cache_dep, get_vector_store_dep
from src.config import get_settings
from src.db.models import User
from src.db.session import get_db
from src.storage.cache import CacheClient
from src.storage.vector import VectorStore

router = APIRouter(prefix="/query", tags=["query"])
settings = get_settings()


class QueryRequest(BaseModel):
    question: str
    collection_tags: list[str] | None = None
    client_request_id: str | None = None  # for mobile idempotency (§8.2)


def _sse_event(event_type: str, data: dict, seq: int) -> str:
    payload = {"event_type": event_type, "seq": seq, **data}
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/stream")
async def stream_query(
    body: QueryRequest,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
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
                db=db,
            ):
                sse = _sse_event(agent_event.event_type, agent_event.payload, agent_event.seq)

                # Buffer for mobile reconnect replay (§8.2)
                await cache.push_stream_event(
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
            yield _sse_event("error", {"message": str(exc)}, 9999)
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
    events = await cache.get_stream_events(query_id, after_seq=last_seq)

    async def replay_generator():
        for i, event in enumerate(events):
            yield _sse_event(
                event.get("event_type", "status"), event, last_seq + i
            )

    return StreamingResponse(replay_generator(), media_type="text/event-stream")
