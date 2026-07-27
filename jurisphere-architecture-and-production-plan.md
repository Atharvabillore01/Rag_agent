# Jurisphere Architecture (reverse-engineered) + DuckVault Production Plan

**Last updated:** 2026-07-26
**Source:** Jurisphere's public OpenAPI spec (`https://api.jurisphere.ai/openapi.json`, ~145 endpoints) + their pricing deck + our own codebase. This documents what their API reveals about how they're built, answers "how do they do unlimited upload," and lays out how to make DuckVault production-ready, fool-proof, and scalable.

---

## 1. What their API reveals about their stack

Their endpoint names, webhooks, and upload protocol give away most of the architecture:

| Signal in the API | What it means |
|---|---|
| `/webhooks/clerk`, HTTPBearer tokens | **Auth is outsourced to Clerk** (managed identity: sign-in, SSO, MFA, org management). They don't build auth themselves. |
| `/library/files/{id}/multipart/{init,sign-part,complete,abort}` + `/upload-url` (signed) | **Direct-to-S3 multipart uploads** — the browser uploads straight to object storage; the API only signs. (This is the "unlimited upload" answer — see §2.) |
| `/library/files/process`, `/tasks`, `/tasks/{id}/retry`, "Temporal workflows" | **Async, durable job orchestration** (Temporal) for parse/OCR/embed, with per-task status + retry. Upload is decoupled from processing. |
| `/payments/razorpay/*` (day-pass, monthly, **topup/{feature}**), `/payments/lemonsqueezy/webhook` | **Usage-based billing** with per-feature top-ups. Razorpay (India) + LemonSqueezy (global). |
| `/organizations/me/usage`, `/citation-usage`, `ContentType` metering | **Org-level metering** — they track and cap the *expensive* things (citations, doctable cells), not storage. |
| Everything is a "matter" (`/matters/{matter_type}`, `DocumentReviewMatter`, `ResearchMatter`, `TimelineMatter`, `DocumentTableMatter`, `CompanyProfileMatter`) | **Unified "matter" abstraction** — every feature is a typed matter row, so listing/sharing/feedback/analytics are generic across features. |
| `/knowledge-bank/*` (separate multipart ingestion + status + retry) | **A second RAG corpus** — the firm's shared knowledge base, ingested separately from per-matter documents. |
| `/clm/{documents,entities,transactions,obligations}` | **Contract Lifecycle Management** — entity/obligation/transaction extraction across a contract portfolio. |
| `/assignments`, `/comments`, `/activity` | **Collaboration layer** — assign matters to people, threaded comments, activity feed. |
| `/library/auto-folderise` | **AI file organization** — suggests + applies a folder structure. |
| `/users/me/memories`, `/organizations/me/memory` | **Persistent memory** at user + org scope (personalization/context). |
| `/consent-documents`, `/users/me/consents` | **Compliance** — explicit consent capture (GDPR/DPDP). |
| `/text-to-speech` (+ voices), `/transcribe`, `/convert-to-excel` | I/O helpers: TTS, speech-to-text, table→Excel export. |
| `/health` + `/readiness` | Separate liveness vs. readiness probes (Kubernetes-style). |
| `/webhooks/typeform`, `/referrals`, `/support/tickets`, `/announcements`, `/analytics` | Growth/ops surface: onboarding forms, referrals, in-app support, announcements, analytics. |
| `X-Jurisphere-Admin-Key`, `/console/organizations/{id}` | A **platform-admin console** separate from org RBAC. |

**Inferred stack:** Clerk (auth) → FastAPI (API, same as us) → **S3 + multipart** (storage) → **Temporal** (async processing) → Postgres (matters/metadata) + a vector DB (RAG) → Razorpay/LemonSqueezy (billing) → SSE (streaming chat). Managed IdP + managed workflow engine + direct-to-object-storage are the three choices that make it scale cheaply.

**The strategic read:** they buy the hard infra pieces (auth, workflow durability, billing) instead of building them, and keep their own engineering on the AI features. Their moat is the corpus + fine-tunes, not the plumbing.

---

## 2. How they provide "unlimited" document upload

Short answer: **the file never touches their API server, storage is cheap, processing is decoupled, and they meter compute instead of storage.** Four mechanics:

1. **Direct-to-S3 multipart upload (browser → S3, bypassing the API).**
   The API only issues a presigned URL (`GET /library/files/{id}/upload-url`) or orchestrates S3's multipart protocol (`init` → `sign-part` (×N) → `complete`). The bytes stream **from the client straight into S3** — the FastAPI process never buffers the file. That removes the classic upload bottleneck (server RAM/bandwidth), so file size is limited only by S3 (5 TB/object), not by their servers.

2. **Multipart = arbitrarily large + parallel + resumable.**
   A file is split into parts, uploaded concurrently, and a failed part retries without restarting the whole upload. This is how a 511-page / 32 MB arbitration filing (from their demo) — or a multi-GB set — uploads reliably.

3. **Object storage is effectively infinite and cheap.**
   S3 scales without provisioning and costs roughly ₹1.5–2 per GB per month. A whole law firm's document set is a few GB. "Unlimited storage" is economically trivial — it's not a real cost lever for them.

4. **Upload is decoupled from processing; they meter the expensive part.**
   After upload they enqueue async jobs (`POST /library/files/process` → Temporal → `/tasks`) to OCR/parse/embed in the background, scaled independently. And per their pricing deck, "unlimited usage" is asterisked: **MCA downloads ₹200/company, "limited doctable cells," citation usage tracked.** So the *upload/storage* is genuinely unlimited, while the *costly AI compute* (extraction cells, citations, lookups) is what's capped. That's the business model: free the cheap thing, meter the expensive thing.

### What DuckVault does today (the gap)
Our upload path streams **through** the API: `documents.py` does `file: UploadFile` → `await file.read()` (whole file into memory) → `object_store.upload(...)`, capped at 100 MB. That caps size, burns server memory, and serializes on API throughput.

### How to match it (concrete, our stack — MinIO is S3-compatible and supports multipart + presigned)
1. Add **presigned single-part upload**: `GET /documents/{id}/upload-url` → return a MinIO presigned PUT URL; the browser PUTs directly.
2. Add **multipart** for large files: `init` / `sign-part` / `complete` / `abort` endpoints wrapping `boto3` `create_multipart_upload` / `generate_presigned_url("upload_part")` / `complete_multipart_upload`. (Boto3 against MinIO does all of this.)
3. Keep a `Document` row in `uploaded` state at init; flip to `uploaded`→`scanning`→… via a **separate `POST /documents/{id}/process`** that enqueues the existing Celery pipeline — so upload and processing are decoupled exactly like theirs.
4. **Meter compute, not storage** — enforce the already-modeled `RateLimitConfig`/`DemoQuota` on the expensive operations (LLM extraction cells, citations, translations) and leave raw upload effectively unlimited.
5. Raise/remove the 100 MB API cap (it no longer applies once bytes bypass the API).

This one change (direct-to-object-storage + async processing + compute metering) is what turns "100 MB through the server" into "unlimited upload."

---

## 3. DuckVault → production-ready, fool-proof, scalable

Our core stack already matches theirs (FastAPI + Postgres + vector DB + Redis + object storage + async workers). Production-readiness is about hardening and scaling each layer. Grouped by concern.

### 3.1 Ingestion & storage at scale
- **Direct-to-S3 multipart** (see §2) — removes the upload bottleneck.
- **Async pipeline hardening:** we have Celery + `IngestionJob`. Add: idempotency keys per stage, exponential backoff (present), a **dead-letter queue** for terminal failures, a `/tasks` status API (mirror theirs), and **backpressure** (bounded queue + per-tenant concurrency so one tenant can't starve others).
- **Wire the `scanning` stage** (already modeled): magic-byte sniff + ClamAV malware scan before parse (currently `uploaded → parsing` skips it).
- **Storage lifecycle:** bucket versioning, lifecycle rules (cold-tier old raw files), per-tenant key prefixes (present), server-side encryption (SSE-S3/KMS).

### 3.2 Compute & AI layer
- **Provider resilience:** circuit breaker + timeout + fallback per LLM provider (task routing already exists; add a fallback model per task so a provider outage degrades, not fails).
- **Cost controls:** token budgets per request, per-tenant daily caps (enforce `RateLimitConfig`), cache identical extractions.
- **Embedding/rerank at scale:** batch embeds; for large corpora move embeddings to a GPU worker pool; Qdrant per-tenant collections (present) with sharding via `TenantVectorIndex` (present) for big tenants.

### 3.3 Data layer scaling
- **Postgres:** connection pooling via **PgBouncer** (SSE holds connections — real risk); read replicas for list/analytics; **partition** high-volume tables (`chunks`, `audit_log`) by tenant or time; indexes are already in place.
- **Qdrant:** per-tenant collections + payload indexes (present); cluster/replicate for HA; snapshot backups.
- **Redis:** separate instances/DBs for cache vs. rate-limit vs. Celery broker (partly done); enable persistence + failover (Sentinel/Cluster).

### 3.4 API & horizontal scale
- **Stateless API** behind a load balancer; N replicas; autoscale on CPU/latency.
- **Workers scale independently** of the API (they already do).
- **Idempotency** on all mutating endpoints (accept `Idempotency-Key`; we already thread `client_request_id` for mobile).
- **Graceful shutdown / draining** for zero-downtime deploys.

### 3.5 Reliability / "fool-proof"
- **No silent failures** (we fixed the OCR-swallow pattern in engines; audit the rest — image parser still fails soft to empty).
- **Health vs. readiness split** (add `/readiness` that checks Postgres/Redis/Qdrant/MinIO — they have both; we have `/health` only).
- **Structured errors** (never stream `str(exc)` to clients — G16), request IDs on every response (present).
- **Timeouts + retries + DLQ** everywhere external (LLM, S3, DB).
- **Comprehensive tests + a staging environment** that mirrors prod; load tests before launch.

### 3.6 Security & compliance (enterprise/legal-grade)
Already done: tenant isolation, RBAC, injection resistance, Phase-0 fixes, MFA, auth throttling, JWT revocation, expanded audit.
Remaining for GA (from `jurisphere-vs-duckvault.md` §7):
- **Encryption at rest** (DB field-level for chunk/result text + bucket SSE/KMS) and **TLS everywhere** between services.
- **SSO (SAML/OIDC)** — either build on our MFA/JWT base, or adopt a **managed IdP (Clerk / WorkOS / Auth0)** like Jurisphere did (faster to enterprise SSO; less to maintain).
- **Secrets manager** (Vault / cloud KMS) + rotation; rotate the currently-exposed Groq key.
- **Consent capture + data-retention/deletion policy** (they have `/consents`; legal buyers need DPA + DPDP/GDPR).
- **SOC 2 / ISO 27001** program (org-level — theirs is only the cloud vendor's; real cert out-positions them).
- **Malware scanning** on upload (§3.1).

### 3.7 Billing & metering
- Enforce `RateLimitConfig`/`DemoQuota` (defined, currently unenforced).
- Add usage metering per feature + a billing integration (Razorpay/Stripe) with plans + per-feature top-ups (mirror their model). Meter compute, not storage.

### 3.8 Observability
- OTEL tracing (config present) → a backend (Tempo/Jaeger); metrics (Prometheus/Grafana): queue depth, job latency, LLM latency/cost, error rates; **error tracking (Sentry)**; structured JSON logs shipped to a store; per-tenant usage dashboards.

### 3.9 Deployment
- Containers (present) → **Kubernetes or ECS**; **IaC** (Terraform); **CI/CD** with migrations gated; blue-green / rolling deploys; autoscaling; per-env config; optional **single-tenant/on-prem** deploy of the same image (our wedge vs. their 50-seat on-prem gate).

---

## 4. Feature-surface deltas their API reveals (that we don't have yet)

Beyond the demo, their API shows product surface we haven't built:
- **Unified "matter" model** — refactor our per-feature tables toward a common matter abstraction (generic list/share/feedback/analytics/assignments).
- **Knowledge Bank** — an org-wide shared RAG corpus (separate from per-matter docs).
- **CLM** — contract portfolio: entities, transactions, obligations extraction + tracking.
- **Collaboration** — assignments, threaded comments, activity feed.
- **Auto-folderise** — AI file organization (we now have folders; not the AI organizer).
- **User + org memory** — persistent personalization/context.
- **Company Profile / MCA** — entity intelligence lookup.
- **TTS + voices**, **convert-to-Excel** (we have transcribe/voice).
- **Billing, usage dashboards, announcements, referrals, in-app support, consents, platform-admin console.**

These are the roadmap past feature-parity — collaboration + knowledge bank + billing are the biggest.

---

## 5. Roadmap to production (sequenced)

**Phase A — make it real (unblock a pilot):**
1. Direct-to-S3 multipart upload + decoupled `process` endpoint (§2) — the "unlimited upload."
2. `cd frontend && npm install` + real build/deploy; `DEBUG=false`, real infra creds, TLS, rotate Groq key.
3. Add real provider keys (Gemini for vision/OCR + Indic translation; a strong `draft` model).
4. Malware scan + `/readiness` + Sentry.

**Phase B — enterprise-grade:**
5. Encryption at rest + secrets manager; SSO/OIDC (or managed IdP); enforce quotas + billing.
6. PgBouncer + read replica; Qdrant HA; DLQ + backpressure.
7. k8s/ECS + Terraform + CI/CD + autoscaling; observability stack.

**Phase C — beat them on product:**
8. Knowledge Bank, CLM, collaboration (assignments/comments), matter model, auto-folderise, memory.
9. SOC 2 / ISO 27001; the legal-corpus strategy (license vs. public-source build).

---

## 6. Bottom line
Their API confirms the plumbing is **standard and buyable** (Clerk + Temporal + S3 + Razorpay); the product engineering is what we've largely matched. To reach production the priorities are: **(1) direct-to-object-storage multipart uploads** (the unlimited-upload mechanic), **(2) deploy/ops hardening + real keys**, **(3) enterprise security/compliance**, and **(4) the collaboration + knowledge-bank + billing surface**. None of it is exotic — it's disciplined hardening of the stack we already run.
