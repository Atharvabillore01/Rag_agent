# Changes — 2026-06-26

Stabilization, observability, and audit-fix pass on the ingestion → query pipeline.

## Root causes fixed (these caused empty results, multi-minute queries, and silent ingestion failures)

- **HuggingFace Xet backend hangs.** Model downloads and on-load update-checks stalled on the Xet transfer backend. Forced plain HTTP via `HF_HUB_DISABLE_XET` in the embed/rerank provider modules.
  - `src/providers/embed/local_embed.py`, `src/providers/rerank/local_rerank.py`
- **macOS Celery worker crash (SIGABRT).** The prefork pool fork()s children, and PyTorch's Metal/MPS backend aborts in a forked process. Worker now auto-selects the `solo` pool on macOS, prefork + autoscale on Linux.
  - `src/ingestion/worker.py`
- **Worker died after one document** ("Future attached to a different loop"). Per-task `asyncio.run()` stranded module-level async singletons (DB engine, Qdrant client) on the first task's loop. Switched to one persistent event loop per worker process.
  - `src/ingestion/worker.py`
- **CPU-unfriendly reranker.** Swapped `BAAI/bge-reranker-v2-m3` (2.3 GB) for `cross-encoder/ms-marco-MiniLM-L-6-v2` (~90 MB), much faster on CPU.
  - `.env` (local, not committed)

## Correctness fixes (from audit)

- **Mark `ready` only after indexing.** Status no longer flips to ready before `embed_and_index`, so an interrupted index can't leave a "ready" doc with no vectors.
- **C1 — no duplicate chunks on retry.** Worker deletes existing chunks for a document before re-persisting.
- **C2 — no orphan vectors on re-ingest.** `embed_and_index` deletes the document's vectors before re-upserting.
- **H3 — no crash for empty tenant.** `VectorStore.search` returns `[]` when the collection doesn't exist yet.
- **page_count populated.** Derived from `len(parsed.pages)` (ParsedDocument has no `page_count` field).
  - `src/ingestion/worker.py`, `src/ingestion/embedder.py`, `src/storage/vector.py`

## Security fixes (from audit)

- **SECRET_KEY fail-fast.** App refuses to start on the insecure default; strong key required via env.
- **CORS** default narrowed from `*` to explicit localhost origins (no `*` + credentials).
- **Rate-limit middleware** now verifies token expiry (removed `verify_exp: False`).
  - `src/config.py`, `src/api/middleware.py`

## Observability

- **Ingestion stage logs** now reach `logs/ingestion.log` (disabled Celery's root-logger hijack; converted structured logs to readable stage lines).
- **Live ingestion progress in the UI.** New SSE endpoint `GET /documents/{id}/events` streams stage transitions; the Documents page shows a per-document pipeline (Parsing → Chunking → Embedding → Indexing).
- Fixed the Documents card subtitle that showed "Processing…" for already-ready docs.
  - `src/ingestion/worker.py`, `src/api/routers/documents.py`, `frontend/src/api/index.js`, `frontend/src/pages/Documents.jsx`

## Ops

- `docker-compose.yml`: Postgres healthcheck targets `ragdb` (`-d ragdb`) to stop FATAL log spam.
- Added `reindex_documents.py` — recovery tool that re-indexes existing Postgres chunks into Qdrant without re-parsing.

## Known open items (not addressed here)

- Rotate the Groq API key.
- Citation `chunk_id` is the Qdrant point UUID, not the DB `Chunk.id`.
- "Hybrid" retrieval builds BM25 only over the dense top-k (no independent keyword recall).
- Token revocation, open self-serve registration, password policy.
