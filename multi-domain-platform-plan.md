# Multi-Domain Vertical Platform — Feature & Distribution Plan

**Status:** Draft v1.0
**Companion to:** `agentic-rag-spec-improved.md` (core platform architecture — this document assumes that platform as the foundation and does not repeat it)
**Trigger:** Reverse-engineered feature set from a competitor demo ("Jurisphere," a legal-AI product) + a decision to productize this platform across multiple professional-services verticals (starting with Legal and Chartered Accountancy/Tax)

---

## 1. What this document covers

Three separable questions, answered in order:

1. **What features turn the current generic RAG platform into a vertical professional-AI product** (the Jurisphere-style capability set: redlining, cited legal/tax research, translation, parallel multi-document review, drafting, voice input, Office integration)?
2. **How do we structure the codebase so the same platform serves multiple professional domains** (Legal, Chartered Accountancy, and others later) **without forking it per domain**?
3. **How do we distribute/deploy it** — one shared SaaS, or separate instances per vertical/client?

---

## 2. Current state — honest gap assessment

The existing platform (`src/`) is a solid **generic multi-tenant RAG core**: FastAPI + Postgres + Qdrant + Redis/Celery + MinIO, with tenants, RBAC (`collection_tags`), quotas, rate limiting, audit logging, and an agentic retrieval loop (`src/agent/planner.py`, `retriever.py`, `verifier.py`, `generator.py`). The frontend (`frontend/src/pages/`) has generic Chat, Documents, Admin, Observability, Login/Register — no domain-specific screens exist yet.

None of the demo-differentiating features exist today:

| Capability seen in the Jurisphere demo | Current state |
|---|---|
| OCR on degraded/scanned documents, any language | English-only Tesseract on standalone images ([src/ingestion/parsers/image.py:51-60](src/ingestion/parsers/image.py#L51-L60)), silent fail-to-empty-string. Marker fallback for scanned PDFs is unverified and untuned ([src/ingestion/parsers/pdf.py:37-66](src/ingestion/parsers/pdf.py#L37-L66)) |
| Translation | None. Zero hits for "translat"/"hindi"/"multilingual" in `src/`. `ParsedDocument.language` field exists but is never set ([src/ingestion/parsers/base.py:19](src/ingestion/parsers/base.py#L19)) |
| Structured field extraction (letter no., parties, dates, amounts) | None |
| Citation-grounded research with click-through to source | Retriever returns chunks (`src/agent/retriever.py`) but no answer-to-source citation linking or click-through UI |
| Redline / diff analysis between two documents | None |
| Parallel Review (N documents → structured comparison table) | None |
| Voice input | None (frontend has no audio capture) |
| Office (Word) add-in | None |
| Domain concept (Legal vs. CA vs. generic) | No `domain` field anywhere on `Tenant` — the platform has no notion of vertical at all |

This is not a criticism of the existing build — it's a correctly-scoped generic RAG core. The gap is entirely in **vertical-specific capability**, which is exactly what this plan adds.

**One architectural tension to flag up front:** the existing spec is explicitly **local-first** (Groq/Ollama/local embeddings, chosen to avoid per-token cloud cost — see `agentic-rag-spec-improved.md` §2.1). High-accuracy OCR+translation on degraded scans (the thing you just saw impress you) realistically requires a frontier vision-capable LLM (Claude vision, GPT-4o, or Gemini) — local vision models (`llava`, `llama3.2-vision`, currently used only for image captioning in `image.py:28-48`) are meaningfully weaker at this specific task. This plan treats scanned-document OCR/translation as a justified, scoped exception to local-first (per-page cost, not per-token chat cost — so the economics are still bounded), while keeping everything else (embeddings, reranking, chat generation) local per the existing spec. Flagging this now so it's a conscious choice, not a silent scope creep.

---

## 3. Target architecture: one core engine, N domain packs

Do **not** fork the codebase per vertical. Fork risk: every bug fix, security patch, and retrieval improvement has to be manually ported N times; two years in, the "Legal" and "CA" codebases have silently diverged and nobody can safely upgrade either. Instead:

```
┌─────────────────────────────────────────────────────────────────┐
│                        CORE ENGINE (shared)                       │
│  Ingestion · Vision OCR+Translate+Extract · Chunking · Embedding   │
│  Hybrid Retrieval · Agent Loop · Redline/Diff Engine               │
│  Parallel Review Engine · Citation Linker · Voice Input · Auth/RBAC│
└───────────────────────────┬─────────────────────────────────────┘
                            │  reads domain config at request time
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────────┐
│  LEGAL PACK     │   │   CA / TAX PACK │   │  (future domain)   │
│  - Prompts       │   │  - Prompts       │   │  - Prompts          │
│  - Skill library  │   │  - Skill library  │   │  - Skill library     │
│  - Citation sources│  │  - Citation sources│  │  - Citation sources  │
│  - Doc taxonomy    │  │  - Doc taxonomy    │  │  - Doc taxonomy       │
│  - Structured       │  │  - Structured        │  │  - Structured          │
│    extraction schemas│ │    extraction schemas│ │    extraction schemas  │
└───────────────┘   └───────────────┘   └───────────────────┘
```

**A "domain pack" is data + config, not code.** Concretely, it's:
- A set of system prompts / agent instructions (`src/agent/prompts.py` becomes domain-parameterized instead of hardcoded)
- A "Skills library" — the pre-built workflow templates seen in the demo (e.g., Legal: "Prepare a brief of judgement," "Change of control tracker"; CA: "GST reconciliation," "ITR sanity check") — stored as structured records (title, prompt template, expected output schema, applicable document types), not Python functions
- A citation-source registry (which external corpora/APIs this domain's research draws from — see §6)
- A document-taxonomy + structured-extraction schema set (what fields to pull out of a "Demand Notice" vs. a "GST Notice" vs. a "Loan Agreement")
- Branding/copy (product name, logo, terminology — e.g., "matter" for Legal vs. "assessment" or "case" for CA)

**Data model change required:** add `domain: Mapped[str]` to `Tenant` (`src/db/models.py`) — e.g., `"legal"`, `"ca"`, `"generic"`. Every prompt-construction, skill-library, and citation-source lookup keys off `tenant.domain`. This is the single field that turns "one platform" into "N products" at request time.

---

## 4. Core (domain-agnostic) features to build

These are the capabilities every vertical needs, built once in the core engine.

### 4.1 Vision-based OCR + Translate + Structured Extraction pipeline
Replace/augment the Tesseract+Marker path: render scanned pages to images, send to a vision-capable LLM in one call that returns `{ocr_text, translated_text (if non-English), detected_language, structured_fields}` as JSON. Requires:
- A new provider: either extend `src/providers/llm/claude.py` to support image content blocks, or add a `gemini.py`/`openai_vision` provider
- Populate the currently-dead `ParsedDocument.language` field and add a DB home for structured fields (new `document_extracted_fields` JSON column, or a `Chunk`-adjacent table)
- Remove the silent `except: return ""` pattern in `image.py` — OCR failures must be visible (retryable failure state, not silent empty text)

### 4.2 Citation-grounded research
Answers cite specific statute sections / case law / regulatory circulars, each clickable to open the underlying source document (as seen in the demo's income-tax Q&A, citing Section 139(4) and *Yash Society v. CIT* with click-through to the scanned judgment). Requires: a citation object in the generator's output schema (source doc ID + page/section), a `Sources` panel in the frontend, and a corpus of authoritative documents per domain (§6) to cite *from* — this only works if the underlying statute/case-law corpus is actually ingested, not invented by the LLM.

### 4.3 Redline / Diff Analysis
Structural diff between two versions of a document (or a document against a "playbook"/standard template), surfaced as a Change → Consequence table. This is a distinct engine from retrieval — it's document-pair alignment + LLM-explained diffs, not a search problem.

### 4.4 Parallel Review (multi-document structured extraction)
User selects N documents + defines a set of questions/column headers → system runs each question against each document (constrained to *only* the selected documents, no external retrieval) → renders a results table. This is effectively "structured extraction as a table," reusable for loan agreements (Legal/Corporate) or GSTR reconciliation (CA) alike — build it once as a generic "N docs × M questions → table" engine.

### 4.5 Drafting assistant
Chat-driven document generation grounded in (a) uploaded case/matter documents and (b) cited authorities from §4.2 — already close to what `src/agent/generator.py` + `planner.py` do for Q&A; drafting is the same loop with a "produce a full document, not an answer" output mode and multi-step revision (append/track-changes rather than replace).

### 4.6 Voice input
Browser `MediaRecorder` → speech-to-text (Whisper, already used elsewhere in your other projects per `whisper-hinglish-demo`) → populates the query box. Frontend-only addition plus one new transcription endpoint.

### 4.7 Office (Word) add-in
Separate small deliverable (Office.js add-in) that calls the same core API — "Ask questions / make changes to this document" and "review against a playbook," exactly as demoed. Build after the web product's drafting + redline engines are solid, since the add-in is a thin client over them.

### 4.8 Matter/file management + history
Partially covered already (`Document.collection_tags`, per-tenant file storage). Needs: folder hierarchy UI, a "History" view of past queries/skill-runs per matter, and file-level context menu (OCR re-process, move, rename) — mostly frontend + a couple of new endpoints, not new architecture.

---

## 5. Distribution model — recommendation

Three options, in order of recommendation:

**A. Single shared platform, domain selected per tenant (recommended to start).**
One deployment, one codebase, one image. `tenant.domain` picks the prompt set/skills/citation sources at request time. Onboarding a CA firm = create a tenant with `domain="ca"`; no new infra. Cheapest to build and operate; every core-engine improvement (better OCR, better retrieval) benefits every vertical instantly. This is what almost every successful vertical-AI SaaS actually runs underneath, even when the marketing sites look like separate products.

**B. Same image, isolated instance per client/vertical (for later, for enterprise/on-prem deals).**
When a client needs data isolation beyond RBAC (regulatory requirement, on-prem deployment, or a white-label reseller deal), deploy the *same* Docker image with a different `.env`/domain config into its own `docker-compose` stack (or k8s namespace). You already have the deployment primitive for this — `docker-compose.yml` + `Dockerfile` — it just gets templated instead of shared. No code fork; only config + infra differs.

**C. Fully separate codebases per domain — not recommended.**
Only justified if the domains eventually need genuinely incompatible data models or compliance regimes (e.g., one domain must run in an air-gapped government cloud with a completely different provider stack). Don't pre-optimize for this; it's a rare outcome and expensive to build toward speculatively.

**Recommendation: build A now, keep B in mind as the "how do we sell one to a big client who wants isolation" answer later, and treat C as a non-goal unless a specific deal forces it.**

---

## 6. Domain Pack: Legal

Directly maps to what the Jurisphere demo showed.

| Feature | Detail |
|---|---|
| Document types / taxonomy | Demand notices, replies, SPAs/SSAs/MSAs, loan agreements, arbitration pleadings, court judgments, redlines |
| Skills library (examples) | Draft reply to demand notice + counterclaim; redline against standard SPA/MSA template; prepare brief of judgement; change-of-control tracker; damages/compensation analysis; cross-examination question drafting |
| Research corpus / citation sources | Bare Acts (Indian Contract Act 1872, Sale of Goods Act 1930, etc.), court judgments (public sources — see licensing note below), tribunal orders |
| Parallel Review use cases | Compare N contracts/loan agreements for key terms (principal, tenure, default clauses, covenants) |
| Structured extraction schemas | Parties, dates, amounts, governing law clause, termination clause, penalty/interest clause |
| Word add-in use case | Redline a live MSA/SPA in place, party substitution, clause rebalancing per playbook |

**Licensing note:** the demo's citation sources implied SCC Online / Live Law-grade case-law databases — these are commercial, licensed legal-research products, not freely scrapable. Building a comparable citation corpus means either (a) licensing a case-law API/database, or (b) building on genuinely public sources (Indian Kanoon-style public judgment repositories, official Bare Acts, government gazette/circular publications) with clear provenance. This is a real cost/BD item, not an engineering one — flag it as a dependency before promising citation coverage depth.

---

## 7. Domain Pack: Chartered Accountancy / Tax

| Feature | Detail |
|---|---|
| Document types / taxonomy | Income tax notices (139/143/148 etc.), GST notices/returns (GSTR-1/3B/9), financial statements, ledgers, invoices, audit working papers, ITRs |
| Skills library (examples) | Draft reply to income-tax/GST notice; ITR/tax-computation sanity check against slab & surcharge rules; audit checklist walkthrough; ratio analysis over financial statements; reconciliation of GSTR-2B vs. purchase register |
| Research corpus / citation sources | Income Tax Act 1961 + Rules, GST Act + Rules + Circulars/Notifications, ICAI standards (SA/AS/Ind AS), CBDT/CBIC circulars, relevant ITAT/HC/SC tax judgments |
| Parallel Review use cases | Reconcile invoices vs. purchase register vs. GSTR-2B across many files; compare loan sanction letters/covenants for a lending due-diligence review; extract key terms across multiple client engagement letters |
| Structured extraction schemas | Invoice/GSTIN/amount/tax-rate fields, notice section reference + due date + demand amount, financial-statement line items for ratio computation |
| Compliance-calendar add-on (CA-specific, no Legal equivalent) | Due-date tracking (GST returns, advance tax, TDS, ROC filings) — a genuinely CA-specific feature worth adding as a differentiator, not present in the Legal pack |

Note the strong feature overlap with Legal (redlining is really "compare document to standard/playbook" in both; Parallel Review is identical mechanics with different columns; citation-grounded research is identical mechanics with a different corpus) — this overlap is exactly why the shared-core-engine architecture in §3 is the right call, not incidental convenience.

---

## 8. Adding a third (or Nth) domain — the checklist

Because "and other domain" should be a config exercise, not a re-architecture, here's what onboarding a new vertical (HR/compliance, real estate, healthcare compliance, whatever comes next) actually requires once §3–§4 exist:

1. Define document taxonomy for the domain (what document types will be uploaded)
2. Write the skills library (5–10 pre-built workflow templates to start)
3. Identify and ingest the citation-source corpus (statutes/standards/precedent for that domain)
4. Define structured-extraction schemas per document type
5. Write domain-specific system prompts/terminology
6. Set `domain="<new>"` on a test tenant and validate end-to-end
7. (Optional) Branding pass on the frontend for that tenant/domain

No new services, no new deployment topology, no core-engine changes — this is the payoff of doing §3 correctly.

---

## 9. Phased roadmap

| Phase | Scope | Depends on |
|---|---|---|
| **0 — Foundation fixes** | Add `tenant.domain` field; wire a vision-capable LLM provider (Claude vision or new Gemini/GPT-4o provider) for OCR; fix silent-failure patterns in `image.py`/`pdf.py`; populate `language` field | Nothing — pure groundwork |
| **1 — Legal pack MVP** | Citation-grounded research (needs a starter Bare-Acts + public judgments corpus ingested); drafting assistant reuse of existing agent loop; basic redline (2-doc diff) | Phase 0 |
| **2 — Parallel Review + Translation** | Generic N-docs×M-questions engine; translation folded into the OCR pipeline from Phase 0 | Phase 0 |
| **3 — CA pack** | Ingest Income Tax Act/GST Act/circular corpus; CA skills library; reuses Phases 1–2 engines entirely — this phase is almost pure domain-pack configuration, which is the architecture validating itself | Phases 1–2 |
| **4 — Office add-in + Voice input** | Thin clients over the now-stable drafting/redline/research engines | Phases 1–2 |
| **5 — Distribution** | Template the Docker Compose stack for Option B (isolated per-client instance) if/when a client needs it; onboard domain #3 using the §8 checklist | Phases 0–4 |

Recommended build order matches the numbering above — Phase 3 (CA) being cheap is the whole point of the shared-core bet; if it isn't cheap when you get there, that's a signal the domain-pack boundary was drawn wrong in Phase 0–2 and worth revisiting before adding a 4th vertical.

---

## 10. Open decisions (yours to make, not mine)

- **Legal citation-source licensing** (§6) — build on public sources only, or budget for a licensed case-law API? This gates how deep "citation-grounded research" can go for Legal.
- **CA citation-source sourcing** (§7) — same question for Income Tax/GST circulars — likely easier (government sources are more freely available than case-law databases) but still needs a real ingestion/maintenance plan (circulars update constantly).
- **Vision-LLM choice for OCR** (§2, §4.1) — Claude vision (consistent with existing Anthropic provider), vs. adding a Gemini/GPT-4o provider purely for this task. Affects §3's provider factory (`src/providers/factory.py`).
- **Third domain identity** — not required to start (§8 makes it a config exercise later), but worth deciding *when* to introduce it so BD/sales messaging doesn't get ahead of what Phase 3 has actually validated.
