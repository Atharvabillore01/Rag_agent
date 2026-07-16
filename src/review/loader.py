"""Load document text for Parallel Review.

Gathers the stored chunk text for a set of documents, tenant-scoped, in
chunk order. Enforces the two invariants the engine relies on: every document
belongs to the requesting tenant (no cross-tenant leakage) and has finished
ingesting (so its text is complete).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Chunk, Document, DocumentStatus

_READY = {DocumentStatus.ready, DocumentStatus.ready_with_warnings}


async def load_document_texts(
    db: AsyncSession,
    tenant_id: str,
    document_ids: list[str],
) -> tuple[list[tuple[str, str, str]], list[str], list[str]]:
    """Return ``(docs, missing_ids, not_ready_ids)``.

    * ``docs`` — ``(doc_id, filename, text)`` for tenant-owned, ready documents,
      in the requested order. ``text`` is the document's chunk text joined in
      ``chunk_index`` order.
    * ``missing_ids`` — requested ids not owned by this tenant (or nonexistent).
    * ``not_ready_ids`` — owned but not finished ingesting, so no reliable text.
    """
    if not document_ids:
        return [], [], []

    res = await db.execute(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.id.in_(document_ids),
        )
    )
    docs_by_id = {d.id: d for d in res.scalars().all()}

    missing = [i for i in document_ids if i not in docs_by_id]
    not_ready = [i for i in document_ids if i in docs_by_id and docs_by_id[i].status not in _READY]
    ready_ids = [
        i for i in document_ids if i in docs_by_id and docs_by_id[i].status in _READY
    ]

    texts: dict[str, list[str]] = {}
    if ready_ids:
        cres = await db.execute(
            select(Chunk.document_id, Chunk.text)
            .where(Chunk.tenant_id == tenant_id, Chunk.document_id.in_(ready_ids))
            .order_by(Chunk.document_id, Chunk.chunk_index)
        )
        for doc_id, text in cres.all():
            texts.setdefault(doc_id, []).append(text or "")

    docs = [(i, docs_by_id[i].filename, "\n".join(texts.get(i, []))) for i in ready_ids]
    return docs, missing, not_ready


async def load_document_chunks(
    db: AsyncSession,
    tenant_id: str,
    document_ids: list[str],
) -> tuple[list[dict], list[str], list[str]]:
    """Like load_document_texts, but returns per-chunk rows WITH page numbers.

    Returns ``(chunks, missing_ids, not_ready_ids)`` where each chunk is
    ``{document_id, filename, chunk_index, page_number, text}``, ordered by
    document (in requested order) then chunk_index. Used by LoD so each extracted
    date can be attributed to the exact page it appears on.
    """
    if not document_ids:
        return [], [], []

    res = await db.execute(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.id.in_(document_ids),
        )
    )
    docs_by_id = {d.id: d for d in res.scalars().all()}
    missing = [i for i in document_ids if i not in docs_by_id]
    not_ready = [i for i in document_ids if i in docs_by_id and docs_by_id[i].status not in _READY]
    ready_ids = [i for i in document_ids if i in docs_by_id and docs_by_id[i].status in _READY]

    out: list[dict] = []
    if ready_ids:
        cres = await db.execute(
            select(Chunk.document_id, Chunk.chunk_index, Chunk.page_number, Chunk.text)
            .where(Chunk.tenant_id == tenant_id, Chunk.document_id.in_(ready_ids))
            .order_by(Chunk.document_id, Chunk.chunk_index)
        )
        by_doc: dict[str, list] = {}
        for doc_id, idx, page, text in cres.all():
            by_doc.setdefault(doc_id, []).append((idx, page, text))
        for i in ready_ids:
            for idx, page, text in by_doc.get(i, []):
                out.append({
                    "document_id": i,
                    "filename": docs_by_id[i].filename,
                    "chunk_index": idx,
                    "page_number": page,
                    "text": text or "",
                })
    return out, missing, not_ready
