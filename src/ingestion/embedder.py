"""Embed chunks and upsert into Qdrant — idempotent (§3.5)."""

import logging
import uuid

from src.ingestion.chunker import RawChunk
from src.providers.factory import get_embed_provider
from src.storage.vector import VectorPoint, VectorStore


EMBED_BATCH_SIZE = 64

# Stable UUID namespace for deterministic chunk point IDs.
# Qdrant requires UUID or unsigned-int IDs — composite strings are rejected.
_CHUNK_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def _chunk_point_id(document_id: str, chunk_index: int) -> str:
    """Return a stable UUID string for a (document, chunk_index) pair."""
    return str(uuid.uuid5(_CHUNK_NS, f"{document_id}:{chunk_index}"))


# Maximum characters stored in the payload text_preview field.
# BM25 in the retriever scores on this field, so truncating too early
# degrades keyword recall on long chunks (512 tokens ≈ 2000 chars).
_TEXT_PREVIEW_MAX = 2000


logger = logging.getLogger(__name__)

async def embed_and_index(
    tenant_id: str,
    document_id: str,
    ingestion_version: int,
    chunks: list[RawChunk],
    vector_store: VectorStore,
    collection_tags: list[str] | None = None,
    document_status: str = "ready",
) -> None:
    """Embed all chunks in batches and upsert into the tenant's Qdrant collection.

    Payload stored per vector includes enough metadata to reconstruct citations
    without a Postgres round-trip (§9.2).
    """
    if not chunks:
        return

    # Only index leaf chunks (children, or single-chunk parents with no children).
    # Parent chunks are stored in Postgres for context lookup but not in Qdrant —
    # indexing both doubles storage and pollutes retrieval with redundant text.
    indexable = [c for c in chunks if c.is_indexable]
    if not indexable:
        return

    embedder = get_embed_provider()

    # ── Batch embed + upsert ──────────────────────────────────────────────────
    # Ensure collection is created before the first upsert.  We learn the vector
    # dimension from the first batch response instead of a throwaway probe call.
    collection_ready = False
    for batch_start in range(0, len(indexable), EMBED_BATCH_SIZE):
        batch = indexable[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [c.text for c in batch]
        batch_end = min(batch_start + len(batch), len(indexable))
        logger.info(
            "embedding batch",
            extra={
                "document_id": document_id,
                "tenant_id": tenant_id,
                "batch_start": batch_start,
                "batch_end": batch_end,
                "total_chunks": len(indexable),
            },
        )

        embed_resp = await embedder.embed(texts)

        if not collection_ready:
            vector_size = len(embed_resp.embeddings[0])
            await vector_store.ensure_collection(tenant_id, vector_size)
            collection_ready = True

        points: list[VectorPoint] = []
        for chunk, embedding in zip(batch, embed_resp.embeddings):
            points.append(
                VectorPoint(
                    # Deterministic UUID so re-ingestion is idempotent (upsert-safe)
                    id=_chunk_point_id(document_id, chunk.chunk_index),
                    vector=embedding,
                    payload={
                        "chunk_index": chunk.chunk_index,
                        "document_id": document_id,
                        "tenant_id": tenant_id,
                        "ingestion_version": ingestion_version,
                        "page_number": chunk.page_number,
                        "section_heading": chunk.section_heading,
                        "chunk_type": chunk.chunk_type.value,
                        "collection_tags": collection_tags or [],
                        "document_status": document_status,
                        # BM25 in retriever.py scores on text_preview — store
                        # enough text for meaningful keyword recall.
                        "text_preview": chunk.text[:_TEXT_PREVIEW_MAX],
                        "embedding_model": embed_resp.model,
                    },
                )
            )

        await vector_store.upsert(tenant_id, points)
        logger.info(
            "vector upsert completed",
            extra={
                "document_id": document_id,
                "tenant_id": tenant_id,
                "batch_start": batch_start,
                "batch_end": batch_end,
                "points": len(points),
            },
        )
