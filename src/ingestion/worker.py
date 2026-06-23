"""Celery ingestion worker — durable state machine with per-stage checkpoints (§3.5)."""

from datetime import datetime, timezone

from celery import Celery
from celery.utils.log import get_task_logger

from src.config import get_settings

settings = get_settings()

celery_app = Celery(
    "rag_ingestion",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    task_track_started=True,
    task_acks_late=True,         # re-queue on worker crash
    worker_prefetch_multiplier=1,
    task_routes={
        "src.ingestion.worker.run_ingestion_pipeline": {
            "queue": settings.ingestion_fast_queue
        },
    },
)

logger = get_task_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@celery_app.task(
    name="src.ingestion.worker.run_ingestion_pipeline",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_ingestion_pipeline(
    self,
    document_id: str,
    tenant_id: str,
    storage_path: str,
    file_type: str,
    ingestion_version: int,
    collection_tags: list[str] | None = None,
):
    """
    Full ingestion pipeline as a single Celery task.

    Stages: download → parse → chunk → embed → index → status=ready

    Each stage writes a checkpoint row in ingestion_jobs so retries can
    resume from the last successful stage.
    """
    import asyncio

    # Use a fresh event loop so we never collide with any loop the Celery
    # worker process may have running (e.g. from gevent/eventlet pools).
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            _async_pipeline(
                task=self,
                document_id=document_id,
                tenant_id=tenant_id,
                storage_path=storage_path,
                file_type=file_type,
                ingestion_version=ingestion_version,
                collection_tags=collection_tags,
            )
        )
    finally:
        loop.close()


async def _async_pipeline(
    task,
    document_id: str,
    tenant_id: str,
    storage_path: str,
    file_type: str,
    ingestion_version: int,
    collection_tags: list[str] | None,
) -> None:
    from sqlalchemy import update

    from src.db.models import Document, DocumentStatus, IngestionJob, IngestionStage
    from src.db.session import AsyncSessionLocal
    from src.ingestion.chunker import chunk_document
    from src.ingestion.embedder import embed_and_index
    from src.ingestion.parsers.router import parse_document
    from src.storage.object import get_object_store
    from src.storage.vector import get_vector_store

    object_store = get_object_store()
    vector_store = get_vector_store()

    async with AsyncSessionLocal() as db:
        async def _set_status(status: DocumentStatus, failure_reason: str | None = None) -> None:
            kwargs = {"status": status, "updated_at": _now()}
            if failure_reason:
                kwargs["failure_reason"] = failure_reason
            await db.execute(
                update(Document).where(Document.id == document_id).values(**kwargs)
            )
            await db.commit()

        async def _checkpoint(stage: IngestionStage, error_code: str | None = None, error_detail: str | None = None) -> None:
            job = IngestionJob(
                document_id=document_id,
                tenant_id=tenant_id,
                stage=stage,
                attempt_count=task.request.retries + 1,
                started_at=_now(),
                finished_at=_now() if not error_code else None,
                error_code=error_code,
                error_detail=error_detail,
            )
            db.add(job)
            await db.commit()

        try:
            # ── Stage 1: Download from object storage ──────────────────────
            await _set_status(DocumentStatus.parsing)
            logger.info(f"[{document_id}] downloading from {storage_path}")
            raw_bytes = object_store.download(storage_path)

            # ── Stage 2: Parse ─────────────────────────────────────────────
            logger.info(f"[{document_id}] parsing as {file_type}")
            parsed = parse_document(raw_bytes, file_type)
            has_warnings = bool(parsed.warnings)

            await _checkpoint(IngestionStage.parsing)

            # ── Stage 3: Chunk ─────────────────────────────────────────────
            await _set_status(DocumentStatus.chunking)
            chunks = chunk_document(parsed, file_type)
            logger.info(f"[{document_id}] produced {len(chunks)} chunks")
            await _checkpoint(IngestionStage.chunking)

            # ── Stage 4: Persist chunk metadata to Postgres ─────────────────
            from src.db.models import Chunk
            from src.providers.factory import get_embed_provider

            embed_prov = get_embed_provider()
            # Use the provider's declared model name, not its class name.
            # All embed providers store it as _model_name (prefixed to avoid
            # collision with pydantic model_config on base classes).
            embed_model = getattr(embed_prov, "_model_name", None) or type(embed_prov).__name__

            # Build a map from raw chunk index → DB chunk id (for parent linking)
            chunk_index_to_id: dict[int, str] = {}

            for raw_chunk in chunks:
                # Resolve parent_chunk_id
                parent_db_id: str | None = None
                if raw_chunk.parent_index is not None:
                    parent_db_id = chunk_index_to_id.get(raw_chunk.parent_index)

                db_chunk = Chunk(
                    document_id=document_id,
                    tenant_id=tenant_id,
                    chunk_index=raw_chunk.chunk_index,
                    text=raw_chunk.text,
                    token_count=max(1, len(raw_chunk.text) // 4),
                    parent_chunk_id=parent_db_id,
                    page_number=raw_chunk.page_number,
                    section_heading=raw_chunk.section_heading,
                    chunk_type=raw_chunk.chunk_type,
                    embedding_model=embed_model,
                    embedding_version="1",
                )
                db.add(db_chunk)
                await db.flush()  # get db_chunk.id without committing
                chunk_index_to_id[raw_chunk.chunk_index] = db_chunk.id

            await db.commit()

            # ── Stage 5: Embed + index ─────────────────────────────────────
            await _set_status(DocumentStatus.embedding)
            await _checkpoint(IngestionStage.embedding)

            # Flip Postgres status to ready BEFORE indexing into Qdrant.
            # This guarantees that Qdrant's document_status="ready" payload filter
            # is always consistent: if Qdrant says ready, Postgres already agrees.
            # The only race window is Postgres=ready, Qdrant=not-yet-indexed, which
            # causes a brief empty result — far safer than the reverse (Qdrant says
            # ready but Postgres hasn't confirmed, exposing in-progress content).
            final_status = (
                DocumentStatus.ready_with_warnings if has_warnings else DocumentStatus.ready
            )
            await _set_status(final_status)

            await embed_and_index(
                tenant_id=tenant_id,
                document_id=document_id,
                ingestion_version=ingestion_version,
                chunks=chunks,
                vector_store=vector_store,
                collection_tags=collection_tags,
                document_status="ready",
            )

            await _checkpoint(IngestionStage.indexing)
            logger.info(f"[{document_id}] ingestion complete → {final_status.value}")

            # Publish status event for Notification Service
            from src.storage.cache import get_cache
            cache = get_cache()
            await cache.set_document_status(tenant_id, document_id, final_status.value)

        except Exception as exc:
            logger.exception(f"[{document_id}] ingestion failed: {exc}")
            retries_left = task.max_retries - task.request.retries

            if retries_left > 0:
                await _set_status(DocumentStatus.failed_retryable, str(exc))
                raise task.retry(exc=exc, countdown=30 * (2 ** task.request.retries))
            else:
                await _set_status(DocumentStatus.failed_terminal, str(exc))
