"""Hybrid retriever — dense vector + BM25 sparse (§4.1, §3.4).

Scalability design for 10,000+ documents:
  - Qdrant is the primary ready-gate and RBAC filter.  Indexed payload fields
    (document_status, collection_tags, document_id) make filters O(log n).
  - Postgres is only consulted when the planner targets specific document IDs
    (for authorization — verify those IDs belong to the tenant before passing
    them to Qdrant).  We NEVER fetch all ready document IDs from Postgres and
    dump them into a Qdrant MatchAny filter — that path kills performance at scale.
  - Per-tenant Qdrant collection provides the outer tenant isolation boundary.
"""

from dataclasses import dataclass

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Chunk as DBChunk, Document, DocumentStatus
from src.providers.factory import embedder, reranker
from src.storage.vector import VectorStore


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    text_preview: str
    page_number: int | None
    section_heading: str | None
    chunk_type: str
    score: float
    collection_tags: list[str]
    chunk_index: int = 0   # needed for parent lookup


class BM25Index:
    """In-memory BM25 for sparse re-scoring over dense candidates."""

    def __init__(self) -> None:
        self._corpus: list[dict] = []

    def build(self, candidates: list[dict]) -> None:
        self._corpus = candidates

    def search(self, query: str, top_k: int = 20) -> list[tuple[dict, float]]:
        try:
            from rank_bm25 import BM25Okapi

            tokenized = [c["text_preview"].lower().split() for c in self._corpus]
            bm25 = BM25Okapi(tokenized)
            scores = bm25.get_scores(query.lower().split())
            ranked = sorted(zip(self._corpus, scores), key=lambda x: x[1], reverse=True)
            return ranked[:top_k]
        except ImportError:
            query_terms = set(query.lower().split())
            results = [
                (doc, float(sum(doc["text_preview"].lower().count(t) for t in query_terms)))
                for doc in self._corpus
            ]
            return sorted(results, key=lambda x: x[1], reverse=True)[:top_k]


_STRATEGY_WEIGHTS = {
    "hybrid": (1.0, 1.0),          # equal dense / sparse
    "keyword_heavy": (0.5, 2.0),   # BM25 dominates
    "semantic_heavy": (2.0, 0.5),  # dense dominates
}


def _reciprocal_rank_fusion(
    dense: list[dict],
    sparse: list[tuple[dict, float]],
    k: int = 60,
    retrieval_strategy: str = "hybrid",
) -> list[dict]:
    dense_w, sparse_w = _STRATEGY_WEIGHTS.get(retrieval_strategy, (1.0, 1.0))
    scores: dict[str, float] = {}
    payloads: dict[str, dict] = {}

    for rank, item in enumerate(dense):
        cid = item["id"]
        scores[cid] = scores.get(cid, 0.0) + dense_w / (k + rank + 1)
        payloads[cid] = item

    for rank, (item, _) in enumerate(sparse):
        cid = item["id"]
        scores[cid] = scores.get(cid, 0.0) + sparse_w / (k + rank + 1)
        payloads[cid] = item

    return [dict(**payloads[cid], rrf_score=scores[cid])
            for cid in sorted(scores, key=lambda c: scores[c], reverse=True)]


async def _expand_with_parent_context(
    chunks: list[RetrievedChunk],
    db: AsyncSession,
) -> list[RetrievedChunk]:
    """Replace child chunk text with parent's full text for generation context.

    This is the second half of hierarchical retrieval:
    - Retrieval uses small child chunks (512 tok) for precise matching.
    - Generation uses the parent's full text (1024 tok) for richer context.

    A child with no parent (it IS a leaf) keeps its own text unchanged.
    Uses two batched Postgres queries regardless of chunk count.
    """
    if not chunks:
        return chunks

    pairs = [(c.document_id, c.chunk_index) for c in chunks]

    # Batch 1: look up parent_chunk_id for every returned child
    child_rows = await db.execute(
        select(DBChunk.document_id, DBChunk.chunk_index, DBChunk.parent_chunk_id)
        .where(tuple_(DBChunk.document_id, DBChunk.chunk_index).in_(pairs))
    )
    child_info: dict[tuple[str, int], str | None] = {
        (row[0], row[1]): row[2] for row in child_rows.fetchall()
    }

    # Batch 2: fetch full text for every parent that exists
    parent_ids = {pid for pid in child_info.values() if pid}
    parent_texts: dict[str, str] = {}
    if parent_ids:
        parent_rows = await db.execute(
            select(DBChunk.id, DBChunk.text).where(DBChunk.id.in_(parent_ids))
        )
        parent_texts = {row[0]: row[1] for row in parent_rows.fetchall()}

    # Expand: swap text_preview for parent text where available
    for chunk in chunks:
        parent_id = child_info.get((chunk.document_id, chunk.chunk_index))
        if parent_id and parent_id in parent_texts:
            chunk.text_preview = parent_texts[parent_id]

    return chunks


async def _authorize_document_ids(
    db: AsyncSession,
    tenant_id: str,
    document_ids: list[str],
) -> list[str]:
    """Return only the document IDs that belong to this tenant and are ready.

    Used when the planner targets specific documents.  This list is always small
    (planner logic), so passing to Qdrant MatchAny is safe.
    """
    result = await db.execute(
        select(Document.id).where(
            Document.tenant_id == tenant_id,
            Document.id.in_(document_ids),
            Document.status.in_([DocumentStatus.ready, DocumentStatus.ready_with_warnings]),
        )
    )
    return [row[0] for row in result.fetchall()]


async def hybrid_retrieve(
    query: str,
    tenant_id: str,
    vector_store: VectorStore,
    db: AsyncSession,
    *,
    top_k: int = 20,
    rerank_top_n: int = 5,
    collection_tags: list[str] | None = None,
    document_ids: list[str] | None = None,
    retrieval_strategy: str = "hybrid",
) -> list[RetrievedChunk]:
    """Vector search + BM25 → RRF → cross-encoder rerank.

    Args:
        collection_tags: scope search to documents tagged with ANY of these tags.
        document_ids:    planner-specified allowlist — authorized against Postgres
                         before passing to Qdrant.  Must remain small (< ~100).
    """
    # ── Optional: authorize planner-specified document IDs ─────────────────────
    authorized_ids: list[str] | None = None
    if document_ids:
        authorized_ids = await _authorize_document_ids(db, tenant_id, document_ids)
        if not authorized_ids:
            return []

    # ── Dense retrieval — Qdrant handles ready-gate + scope via payload indexes ─
    embed_prov = embedder()
    embed_resp = await embed_prov.embed([query])
    query_vector = embed_resp.embeddings[0]

    dense_hits = await vector_store.search(
        tenant_id=tenant_id,
        query_vector=query_vector,
        top_k=top_k,
        collection_tags=collection_tags,
        document_ids=authorized_ids,
    )

    if not dense_hits:
        return []

    # ── Sparse retrieval (BM25 over dense candidates) ─────────────────────────
    bm25 = BM25Index()
    bm25.build(dense_hits)
    sparse_hits = bm25.search(query, top_k=top_k)

    # ── RRF fusion ─────────────────────────────────────────────────────────────
    candidates = _reciprocal_rank_fusion(dense_hits, sparse_hits, retrieval_strategy=retrieval_strategy)[:top_k]

    # ── Cross-encoder rerank ───────────────────────────────────────────────────
    rerank_prov = reranker()
    texts = [c.get("text_preview", "") for c in candidates]
    rerank_results = await rerank_prov.rerank(query, texts, top_n=rerank_top_n)

    retrieved = [
        RetrievedChunk(
            chunk_id=candidates[rr.index]["id"],
            document_id=candidates[rr.index].get("document_id", ""),
            text_preview=candidates[rr.index].get("text_preview", ""),
            page_number=candidates[rr.index].get("page_number"),
            section_heading=candidates[rr.index].get("section_heading"),
            chunk_type=candidates[rr.index].get("chunk_type", "prose"),
            score=rr.score,
            collection_tags=candidates[rr.index].get("collection_tags", []),
            chunk_index=candidates[rr.index].get("chunk_index", 0),
        )
        for rr in rerank_results
        if rr.index < len(candidates)
    ]

    # Expand child chunks → parent text for richer generation context.
    # This completes the hierarchical retrieval design: small chunks for
    # matching precision, large parent windows for answer quality.
    return await _expand_with_parent_context(retrieved, db)
