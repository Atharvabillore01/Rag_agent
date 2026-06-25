"""Re-index already-parsed documents into Qdrant.

Recovery tool: when ingestion completed parsing/chunking (chunks exist in
Postgres) but the embed+index step was interrupted, this rebuilds the vectors
in Qdrant from the existing chunks WITHOUT re-parsing or duplicating chunks.

Usage:
    python reindex_documents.py            # re-index all ready documents
    python reindex_documents.py <doc_id>   # re-index one document
"""

import asyncio
import sys

from sqlalchemy import select

from src.db.models import Chunk, Document, DocumentStatus
from src.db.session import AsyncSessionLocal
from src.ingestion.chunker import RawChunk
from src.ingestion.embedder import embed_and_index
from src.storage.vector import get_vector_store


async def reindex_document(db, doc: Document, vector_store) -> int:
    rows = (
        await db.execute(
            select(Chunk)
            .where(Chunk.document_id == doc.id)
            .order_by(Chunk.chunk_index)
        )
    ).scalars().all()

    if not rows:
        print(f"  [{doc.id}] no chunks found — skipping")
        return 0

    # Rebuild RawChunks. These DB chunks are all leaves (no parents), so every
    # one is indexable. Parent linkage is irrelevant for vector indexing.
    chunks = [
        RawChunk(
            text=c.text,
            chunk_index=c.chunk_index,
            chunk_type=c.chunk_type,
            page_number=c.page_number,
            section_heading=c.section_heading,
            parent_index=None,
            is_indexable=True,
        )
        for c in rows
    ]

    print(f"  [{doc.id}] {doc.filename}: embedding {len(chunks)} chunks ...")
    await embed_and_index(
        tenant_id=doc.tenant_id,
        document_id=doc.id,
        ingestion_version=doc.ingestion_version,
        chunks=chunks,
        vector_store=vector_store,
        collection_tags=doc.collection_tags or [],
        document_status="ready",
    )
    print(f"  [{doc.id}] done — {len(chunks)} vectors upserted")
    return len(chunks)


async def main() -> None:
    target_id = sys.argv[1] if len(sys.argv) > 1 else None
    vector_store = get_vector_store()

    async with AsyncSessionLocal() as db:
        stmt = select(Document).where(
            Document.status.in_(
                [DocumentStatus.ready, DocumentStatus.ready_with_warnings]
            )
        )
        if target_id:
            stmt = select(Document).where(Document.id == target_id)

        docs = (await db.execute(stmt)).scalars().all()
        if not docs:
            print("No matching documents found.")
            return

        print(f"Re-indexing {len(docs)} document(s):")
        total = 0
        for doc in docs:
            total += await reindex_document(db, doc, vector_store)
        print(f"\nFinished. {total} vectors upserted across {len(docs)} document(s).")


if __name__ == "__main__":
    asyncio.run(main())
