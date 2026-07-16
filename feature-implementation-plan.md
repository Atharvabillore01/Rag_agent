# DuckVault — Feature Implementation Plan

**Status:** Living document — updated as each feature lands.
**Companion to:** `multi-domain-platform-plan.md` (architecture) and `jurisphere_demo_findings.md` (feature source).
**Working method (agreed):** For each feature — (1) spec it here, (2) implement it component-by-component, (3) audit it *completely* (end-to-end, against the running stack), (4) only then mark it solid and move to the next.

---

## 0. Environment reality that shapes sequencing

Verified on 2026-07-15 against the live stack:

- **Working LLM key: Groq only** (`llama-3.3-70b-versatile`, text-only). `anthropic_api_key` (10 chars) and `openai_api_key` (6 chars) are placeholders, not real keys.
- Postgres, Qdrant, Redis, MinIO reachable; local BGE embeddings/reranker in use by the running app.
- Frontend `node_modules` is **partially installed** (`vite/dist`, `lucide-react/dist` missing) — the web build cannot run here until `cd frontend && npm install`. Frontend code is therefore audited statically, not build-run, until deps are restored.

**Consequence:** features that need only a *text* LLM + Postgres are fully verifiable now. **Vision OCR + Translation is deferred** until a vision-capable key (Anthropic/OpenAI/Gemini) or a local Ollama vision model is available — it can be *built* any time but not *audited* without one.

---

## 1. Build order

| # | Feature | Verifiable now? | Why this order |
|---|---|---|---|
| **1** | **Parallel Review** (N docs × M questions → table) — ✅ DONE, audited | ✅ Yes (Groq + Postgres) | Self-contained, no new deps, high-value, prominent in the demo. Establishes the structured-extraction pattern reused elsewhere. |
| **1.5** | **Multi-model routing & provider registry** (task→model; add Gemini/others) | ⚙️ Build + unit-test now; live calls need each provider's key | Cross-cutting: lets every feature pick the right/cheapest model (open + closed). The demo's "many LLMs" claim is this pattern. Foundation already exists — see §5. |
| 2 | Citation-grounded research | ✅ Engine yes; needs a corpus to be meaningful | Builds on existing retriever/generator; adds citation objects + click-through. |
| 3 | Redline / document diff | ✅ Yes | Distinct pair-alignment engine; reuses the structured-LLM-call pattern from #1. |
| 4 | Drafting assistant | ✅ Yes | Existing agent loop in "produce a document" mode. |
| 5 | Vision OCR + Translation + structured extraction | ⛔ Needs vision key/model | Completes ingestion; every earlier feature improves once scans are readable. |
| 6 | Voice input | ✅ (Whisper) | Thin client over transcription. |
| 7 | Office (Word) add-in | — | Thin client over #3/#4 once stable. |

Domain packs (legal / CA prompt sets, skills libraries, citation corpora) layer onto features 1–5 via the `tenant.domain` hook already in place.

---

## 2. The "audit completely" standard (applied to every feature)

A feature is **solid** only when all of these pass:

1. **Compiles / imports** — `py_compile` on all new/changed modules; no import errors.
2. **Unit** — pure functions (parsers, key derivation, JSON extraction) tested with known inputs.
3. **End-to-end on the live stack** — the real path exercised: DB rows in, real LLM call, correct structured output out. For extraction features, use *synthetic documents with known values* and assert the model returns them.
4. **Tenant isolation** — cross-tenant access denied (a tenant cannot review another tenant's documents or read another tenant's results).
5. **Failure modes** — bad input (unknown doc id, empty doc, malformed LLM JSON) degrades gracefully, no 500 crash, no silent empty success.
6. **Cleanup** — any test data created is removed; migrations are reversible.
7. **No regressions** — existing endpoints/models still import and the migration chain still resolves to a single head.

---

## 3. FEATURE 1 — Parallel Review

### 3.1 What it is
User selects **N documents** and defines **M questions** (column headers). The system answers each question for each document, **using only the selected documents (no external retrieval / no other tenant data)**, and returns a **results table** (rows = documents, columns = questions). Sessions persist so past reviews are re-viewable ("recent Parallel Review usage" in the demo), and columns can be added to an existing review. This is the loan-agreement extraction shown at demo 23:15–32:00.

Generic engine, domain-agnostic: the same mechanics serve legal loan-agreement terms or CA invoice/GST fields. Domain packs later supply *pre-built question templates* (e.g. "Exhibit Analysis"); the engine itself takes arbitrary questions.

### 3.2 Components
1. **DB model** `ParallelReview` (+ idempotent migration `0002`):
   - `id`, `tenant_id` (FK, cascade), `created_by` (FK users, set null)
   - `name` (str)
   - `document_ids` (JSON: list of document ids in the review)
   - `questions` (JSON: list of `{key, header, question}`)
   - `results` (JSON: `{doc_id: {filename, answers: {key: answer}, truncated: bool, error: str|null}}`), nullable until computed
   - `status` (str: `pending|running|complete|failed`)
   - `created_at`, `updated_at`
   - Indexes on `tenant_id`, `(tenant_id, created_at)`.
2. **Engine** `src/review/engine.py`:
   - `ReviewQuestion(key, header, question)` dataclass.
   - `answer_document(llm, filename, text, questions, *, max_chars)` → `{key: answer}` via one JSON-mode LLM call, defensive JSON parsing, "Not found" when absent.
   - `run_review(llm, docs, questions, *, concurrency)` → per-doc answers, docs processed concurrently under a semaphore.
3. **Doc-text loader** — gather each selected document's chunk text from Postgres (ordered by `chunk_index`), concatenated and capped per doc; flag truncation.
4. **API** `src/api/routers/review.py`:
   - `POST /review/` (editor) — create + run; validates every doc belongs to the tenant and is `ready`; derives question keys from headers.
   - `GET /review/` (viewer) — recent reviews for the tenant (summary).
   - `GET /review/{id}` (viewer) — full review + results, tenant-scoped.
   - `POST /review/{id}/columns` (editor) — append questions, run only the new ones across docs, merge.
   - `DELETE /review/{id}` (editor).
   - Registered in `src/api/main.py`.
5. **Frontend** `ParallelReview.jsx` page + sidebar nav + `review` API client (built; not build-verified here — see §0).

### 3.3 Acceptance criteria
- Creating a review over 2 synthetic loan docs with distinct principal amounts returns a table where each doc's `principal_amount` cell matches its known value.
- A review scoped to tenant A cannot include or read tenant B's documents/results (404/403).
- An empty document yields `"Not found"`/graceful cell, not a crash.
- Malformed LLM JSON is caught → cell error, review still returns.
- Adding a column re-runs only the new question and merges without recomputing existing cells.
- Migration `0002` applies idempotently and `alembic heads` shows a single head.

### 3.4 Audit protocol (this feature)
Insert synthetic tenant + 2 documents + chunks with known text via a script → call the router functions directly against the live DB + Groq → assert extracted values → test tenant isolation + empty-doc + bad-json paths → clean up. (Mirrors §2.)

### 3.5 Status
- [x] Model + migration 0002 (applied to live DB; single Alembic head)
- [x] Engine (`src/review/engine.py`) — pure helpers unit-tested; extraction deterministic
- [x] Doc-text loader (`src/review/loader.py`)
- [x] API router (`src/api/routers/review.py`) + registered in `main.py`
- [x] **Backend end-to-end audit — 19/19 checks pass** on the live stack (Groq + Postgres)
- [x] Frontend page + nav + client (static-audited — icons/tokens/imports/routes verified; web build blocked by partial node_modules, see §0)

**Feature 1 is SOLID.** Backend fully verified end-to-end on the live stack; frontend built to match existing patterns and static-audited.

**Bug caught by the audit (fixed):** `add_columns` built its merged results with a shallow `dict(rv.results)` copy and mutated nested dicts in place. On a plain SQLAlchemy `JSON` column that leaves change-detection unable to see a diff, so the UPDATE was silently skipped — added columns' answers never persisted (while the `questions` list, reassigned to a new object, did). Fixed with `copy.deepcopy` before mutating + `flag_modified(rv, "results"/"questions")`. This is the failure mode the "audit completely" standard exists to catch.

---

## 5. FEATURE 1.5 — Multi-model routing & provider registry

### 5.1 Reframing "they use 64 LLMs"
That is a **multi-model routing architecture**, not 64 distinct trained models. Production legal/finance-AI tools route each *sub-task* to the model that does it best or cheapest, and a single user request fans out into many model *invocations* across a pipeline (route → retrieve → extract → draft → verify → translate → OCR). Count the invocations across an agentic run over many documents and "dozens of LLM calls" is ordinary. The mix is exactly as you guessed: **open models** (Llama via Groq/Ollama — cheap, local, fast) for classification/extraction/reranking, and **closed models** (Gemini / Claude / GPT-4o — stronger, paid) for vision OCR, hard drafting, and final verification.

### 5.2 What already exists (good news)
The codebase is already provider-agnostic and most of the way there:
- `src/providers/factory.py` — a factory over **groq / openai / azure_openai / claude / ollama**, all behind one `LLMProvider` interface.
- A **router vs. main** split already exists (`llm_router_model` = cheap model for classification; `llm_model` = main model) — the seed of task-based routing.
- **Per-tenant overrides** (`tenants.llm_provider_override` / `llm_model_override`) + a cached `get_tenant_llm(...)`.

So "use several models" is an *extension*, not a rebuild.

### 5.3 What to build
1. **Gemini/Google provider** — `src/providers/llm/gemini.py` implementing `LLMProvider` (+ a `google` case in the factory + `google_api_key` setting). Gemini is a strong, cost-effective vision+text model and a natural default for OCR/translation (Feature 5).
2. **Task-based model selection** — generalize the router/main split into named tasks. Add settings like `llm_extract_model`, `llm_draft_model`, `llm_vision_model`, `llm_translate_model` (each optional, falling back to `llm_model`), and a `get_llm_provider(task=...)` selector. Features then request a model *by task* instead of hardcoding one — e.g. Parallel Review asks for the `extract` task, drafting for `draft`, OCR for `vision`.
3. **(Optional) ensemble / cross-check** — for high-stakes outputs, run 2 models and reconcile (a cheap adversarial-verify pattern). Defer until a feature needs it.

### 5.4 Verifiability & constraint
The provider class + routing layer + factory wiring are **buildable and unit-testable now** (mock/inspect selection). **Live calls to Gemini/Claude/GPT-4o need their API keys**, which aren't present yet (only Groq works — see §0). So this feature ships the *plumbing* now and becomes fully live per-provider as each key is added — the same posture as Vision OCR (Feature 5), which depends on this.

### 5.5 Status — DONE (plumbing), live per-provider as keys are added
- [x] **Gemini provider** (`src/providers/llm/gemini.py`) — text + vision (`complete_with_images`), lazy SDK import
- [x] **Generic OpenAI-compatible provider** (`src/providers/llm/openai_compatible.py`) — Together/Fireworks/OpenRouter/HF/vLLM/local + **fine-tuned open models**
- [x] **Hugging Face** preset (openai_compatible pointed at the HF router)
- [x] Vision method on the base interface (`supports_vision` + `complete_with_images`)
- [x] **Task routing** — `LLMTask` + `get_llm_for_task(task)` + `get_tenant_task_llm(task, ...)` + 7 per-task env overrides, all falling back to base (so Groq-only is unchanged)
- [x] Parallel Review extraction routed through the `extract` task
- [x] `.env.example` + `requirements.txt` (google-genai) documented
- [x] Unit audit: task resolution correct for fallback / provider-default-model / explicit / open-model cases; providers instantiate; **PR 19-check re-run green (no regression)**
- [ ] Live per-provider audit — pending real keys for gemini / claude / openai / a hosted open model

### 5.6 Recommended model per task (best + cheap)
Defaults fall back to base (Groq) so nothing here is required — set the env override to opt a task onto a better/cheaper model.

| Task | Cheap / open (good) | Best / closed (strong) | Notes |
|---|---|---|---|
| `route` | Llama-3.1-8B (Groq) · local 3B (Ollama) | — | Classification/JSON gating; small models suffice. |
| `extract` | **Gemini 2.0 Flash** · Llama-3.3-70B (Groq) | GPT-4o · Claude Sonnet | Parallel Review / field pull. Flash is cheap and strong at JSON. |
| `vision` (OCR) | Qwen2-VL / Llama-3.2-Vision (self-host) | **Gemini 2.0 Flash / 1.5 Pro** · GPT-4o | Your instinct is right — **Gemini is the cheap+accurate default for complex-doc OCR**. |
| `translate` | **IndicTrans2 / NLLB** (open, via openai_compatible) | Gemini 2.0 Flash | For Indian languages a fine-tuned open MT model can beat generalists and is cheap. |
| `draft` | Llama-3.3-70B (Groq) | **Claude Sonnet** · Gemini 1.5 Pro · GPT-4o | Long-form legal/CA drafting wants the strongest reasoning. |
| `verify` | Llama-3.3-70B | A model **different** from `draft` | Independence catches the drafter's own mistakes (adversarial cross-check). |
| `embed` / `rerank` | BGE-large / BGE-reranker (local) | Voyage / Cohere | Already local; multilingual: swap to BGE-M3 for non-English corpora. |

### 5.7 On fine-tuned & open-source (HF) models — your question
You can absolutely use open-source / fine-tuned models for specific tasks. The mechanism is the **`openai_compatible` provider**: fine-tune an open base (Llama/Qwen/Mistral) on legal or CA data, host it behind any OpenAI-compatible server (vLLM, TGI, Together, Fireworks, an HF Inference Endpoint), and point a task's provider at `openai_compatible` (or `huggingface`). No code change — just env. Good fine-tune candidates: a **clause/document classifier** (`route`), a **field extractor** (`extract`), or an **Indic translator** (`translate`) — narrow tasks where a small fine-tune rivals a frontier model at a fraction of the cost.

### 5.8 How the demo generates documents (drafting)
Document generation = **retrieval-augmented drafting**, not a single prompt. The pattern (this is Feature 4): gather the matter's own documents + any cited authorities via retrieval → feed them as grounded context to a strong `draft`-task model → generate a full structured document (letter/notice/reply) with section scaffolding, streamed live → optionally a `verify`-task pass and a citation check. The demo's KGMI reply (research Indian statutes/case-law → produce a formal reply + counterclaim with an authorities annexure) is exactly this loop. Feature 1.5 gives it the right model per step; Feature 4 builds the drafting loop itself.

---

## 7. FEATURE 2 — Citation-grounded research

### 7.1 What it is & the gap
Answers should cite the specific source behind each claim, and those sources should be **readable and click-through** (open the document at the right page), as in the demo's income-tax Q&A. The agent already retrieves, streams, parses a citations block, and emits `citation` + `final_answer` events (`src/agent/loop.py`, `src/agent/generator.py`). The gaps to demo-grade grounding:
1. Citations resolve only to a `document_id` UUID — no **filename**, page snippet, or number, so a Sources panel can't show or link them cleanly.
2. The fallback cites **every** retrieved chunk (noise) instead of the ones actually used.
3. No **numbered inline `[n]`** linkage between a claim and its source.

### 7.2 Components
1. **Prompt** (`prompts.py`) — number chunks `[n]` in context; instruct the model to cite claims inline as `[n]` and end with a `SOURCES: 1, 3` line (numbers, not UUIDs — models copy small ints reliably, UUIDs unreliably).
2. **Generator** (`generator.py`) — `_format_chunks` prefixes each chunk with its `n`; `Citation` gains `number`/`filename`/`snippet`; `_parse_answer_and_citations` maps the `SOURCES:` numbers back to chunks, enriches with filename (from doc-name map) + snippet + page, strips the trailer, and falls back to the **top few** chunks (not all) when the model emits none.
3. **Loop** (`loop.py`) — pass the id→filename map into the parser; emit the enriched fields in `citation` events and `final_answer`.
4. Click-through already possible via existing `GET /documents/{id}/view-url`; frontend Sources panel is additive (static-audited only — build blocked).

### 7.3 Acceptance criteria
- A fact present in only one of two supplied documents is cited to **that** document's chunk (correct attribution), with a resolvable filename.
- `SOURCES: 1, 3` maps to exactly chunks 1 and 3; the `SOURCES:` line is stripped from the displayed answer.
- No `SOURCES:` emitted → fallback cites the top ≤3 chunks, not all.
- Citations carry document_id + chunk_id + page + filename + snippet (superset — backward compatible).

### 7.4 Audit
Call `generate_answer(question, chunks, doc_names=...)` directly with hand-built `RetrievedChunk`s from two synthetic docs + real Groq (no Qdrant needed): assert correct source attribution, filename enrichment, SOURCES parse, trailer-strip, and fallback. (Full retrieval path via Qdrant is exercised separately in the live app.)

### 7.5 Status — DONE (backend), audited
- [x] Prompt numbering + `SOURCES:` instruction (`prompts.py`)
- [x] Generator: enriched `Citation` (number/filename/snippet) + numbered `SOURCES` parse + precise top-3 fallback (`generator.py`)
- [x] Loop: filename-enriched citation events + `final_answer` (`loop.py`)
- [x] **Backend audit — 12/12** (parser unit tests + live Groq: correct source attribution, filename enrichment, SOURCES strip, fallback). Fixed a pre-existing `SyntaxWarning` in the generator prompt while here.
- [ ] Frontend Sources panel (additive; web build blocked — the citation payload already carries number/filename/page/snippet for it)

**Feature 2 backend is SOLID.** Grounded, numbered, click-through-ready citations verified end-to-end on the live LLM.

---

## 8. FEATURE 3 — Redline / document diff

### 8.1 What it is
Compare two documents (a base and a revised version — or a document against a standard "playbook" template) and surface every change as a **Change → Consequence** table, as in the demo's SPA redline. Each row: what changed (insertion / deletion / modification) and its legal/business impact.

### 8.2 Design — deterministic diff, LLM only for consequence
Pure-LLM diffing of two long documents hallucinates and is expensive. So:
1. **Deterministic diff** (`difflib.SequenceMatcher` over paragraph segments) finds the *actual* changed regions — grounded, reproducible, free.
2. **LLM explains consequence** — the real changes are batched into one JSON-mode call that returns `{change, consequence}` per change. The model characterizes impact; it never invents the diff.

This keeps the expensive/unreliable part (impact reasoning) bounded and the factual part (what changed) exact.

### 8.3 Components
1. **DB model** `Redline` (+ migration `0003`): id, tenant_id, created_by, name, base_document_id, revised_document_id, results (JSON list of `{change_type, before, after, change, consequence}`), status, timestamps.
2. **Engine** `src/redline/engine.py`: `compute_changes(base, revised)` (paragraph diff → typed changes, capped) + `explain_changes(llm, changes)` (batched JSON consequence).
3. **Loader**: reuse `src/review/loader.load_document_texts` (tenant-scoped, ready-gated).
4. **API** `src/api/routers/redline.py`: create / list / get / delete; routed through the `extract` task; registered in `main.py`.
5. **Frontend** `Redline.jsx` + nav + client (static-audited; build blocked).

### 8.4 Acceptance criteria
- Two docs differing by a known clause edit (e.g. governing law Singapore→India, interest 12%→18%) yield changes of the right **type** with those before/after values, each with a non-empty consequence.
- Identical documents → zero changes (no hallucinated diffs).
- Cross-tenant docs rejected (404); not-ready docs rejected (400).
- Deterministic diff is unit-tested independently of the LLM.

### 8.5 Audit
Unit-test `compute_changes` on synthetic before/after (insertion/deletion/modification detected). Then end-to-end on the live stack: synthetic base + revised contract with known edits → create redline → assert changes + consequences + attribution; identical-docs → empty; isolation; cleanup.

### 8.6 Status — DONE, audited
- [x] Model + migration `0003` (applied to live DB; single Alembic head)
- [x] Engine (`src/redline/engine.py`) — deterministic diff + **per-clause split** of contiguous 1:1 replacements + batched LLM consequence
- [x] API router (`src/api/routers/redline.py`) + registered in `main.py` (routed via `extract` task)
- [x] **Backend end-to-end audit — 15/15** on the live stack (known clause edits detected with correct types + consequences; identical docs → 0 changes; isolation; same-id/not-ready rejected)
- [x] Frontend `Redline.jsx` + nav + client (static-audited)

**Feature 3 is SOLID.** The audit caught (and I fixed) a diff-granularity issue — contiguous multi-clause edits were merged into one row; now each clause change is its own Change→Consequence row.

### 8.7 Update model note
`Update your document against a playbook` (demo) is the same engine with the base = a standard template document — a thin future variant, not new architecture.

---

## 9. FEATURE — Document Translation

### 9.1 What it is & relation to Feature 5
Translate a document into a target language, viewable side-by-side (the demo's Translation module — the Hindi→English UP-Awas letter). This is the **verifiable-now half** of the planned "Vision OCR + Translation" (Feature 5): translating *text* needs only a text LLM (works today on Groq); the OCR-of-scans half still needs a vision key. The two compose — Vision OCR (later) produces text → this feature translates it.

### 9.2 Components
1. **DB model** `Translation` (+ migration `0004`): id, tenant_id, created_by, document_id, target_language, source_text (optional preview), result (translated text), status, timestamps.
2. **Engine** `src/translation/engine.py`: `translate_text(llm, text, target_language)` — splits long text into segments on paragraph boundaries, translates each (bounded concurrency, transient-retry), joins in order. Plain-text output (not JSON); preserves names/numbers/dates/formatting.
3. **Routing**: uses `LLMTask.TRANSLATE` — falls back to Groq now, points to Gemini / IndicTrans2 (open) later via env, no code change.
4. **Loader**: reuse `load_document_texts` (single doc, tenant-scoped, ready-gated).
5. **API** `src/api/routers/translation.py`: create / list / get / delete; registered in `main.py`.
6. **Frontend** `Translation.jsx` + nav + client (static-audited).

### 9.3 Acceptance criteria
- A short foreign-language document (e.g. French/Hindi) → English translation that **preserves facts** (numbers, dates) and reads as the target language (source-language tokens gone).
- Round-trip sanity: English → Spanish output differs from input and contains expected target tokens.
- Cross-tenant doc rejected (404); not-ready rejected (400).
- Long text is segmented and re-joined in order (segmentation unit-tested).

### 9.4 Audit
Unit-test the segmenter. End-to-end on the live stack: synthetic doc "Le montant total est de 5000 euros. La date limite est le 15 octobre." → translate to English → assert output contains "5000" and "October"/"15", no "octobre"; tenant isolation; cleanup.

### 9.5 Status
- [ ] Model + migration 0004
- [ ] Engine (segment + translate + join)
- [ ] API router + registration
- [ ] Backend end-to-end audit
- [ ] Frontend (static-audited)

---

## 10. Competitive intelligence — Jurisphere pricing & product deck (2026-07)

Source: `Jurisphere Pricing(Less than 100).pdf` (their sales deck). This is the competitor we're benchmarking DuckVault against.

> **Full, exhaustive comparison lives in [`jurisphere-vs-duckvault.md`](jurisphere-vs-duckvault.md)** — feature-by-feature parity matrix (down to UX micro-details), a 26-row security & compliance table with DuckVault `file:line` refs, pricing, moat analysis, a prioritized "what to implement" list, and a security-hardening roadmap (`G1`–`G22`). The summary below is the condensed view; that doc is the source of truth.

### 10.1 Their pricing (per user / year, INR, ex-taxes, ex-on-prem)
| Users | Price/user/yr | ~Annual (low end of band) |
|---|---|---|
| Up to 10 | ₹1,60,000 | ₹16L for 10 |
| 11–25 | ₹1,20,000 | ₹13.2L–₹30L |
| 26–50 | ₹72,000 | ₹18.7L–₹36L |
| 51–100+ | ₹60,000 | ₹30L–₹60L+ |

- Annual billing; "unlimited usage" login-based; **on-prem only above 50 logins**; MCA downloads ₹200/company; "limited doctable cells." So the market pays **₹60k–₹1.6L per seat/year** — a premium anchor for our own pricing.

### 10.2 Feature parity — what we've already built vs. them
| Jurisphere feature | DuckVault status |
|---|---|
| Parallel Reviewer (multi-doc → table, download Word) | ✅ Feature 1 (built, audited) |
| Redline Analysis (line/word change table) | ✅ Feature 3 (built, audited) |
| Inline citations → open doc, scroll, highlight | ✅ Feature 2 backend (built); scroll+highlight UI is a frontend add |
| Translation (100+ langs, 22 Indian langs, poor scans) | ✅ Feature (text) built; Indian-lang quality + scan OCR need Gemini/IndicTrans2 + Feature 5 vision |
| Legal Research (agentic, grounded) | ◑ We have an agent loop; theirs is master + 3 sub-agents (web/legislation/judgements) on an Indian corpus |
| Document Analysis ("talk to documents", summarize judgements) | ◑ Covered by chat/query |
| **LoD Builder (List of Dates / chronology)** | ❌ **not built — strongest next-feature candidate** |

### 10.3 Their moat (and what it means for us)
- **Indian Legal corpus: ~15.1M documents + fine-tuned models + legal knowledge graph.** This is the content/licensing dependency flagged in `multi-domain-platform-plan.md` §6 — the real cost/BD item, not engineering.
- **Fine-tuned models** — confirms the "some LLMs are fine-tuned" intuition; our `openai_compatible` provider (Feature 1.5) is exactly the plug for hosting fine-tunes.
- Security posture: Azure + GCP, SOC2 + ISO27001, encryption. Team ex-AZB/CAM/Khaitan + IIT/BITS.

### 10.4 Roadmap implications
1. **Build LoD Builder next** — it's their headline litigation feature and our only clear parity gap; it's another structured-extraction variant (dates + event summary + source doc + page + citation), fully verifiable now on Groq. 
2. Translation quality for Indian languages → route the `translate` task to Gemini or a fine-tuned IndicTrans2 via `openai_compatible` (already possible, needs a key/host).
3. Citation UX → add the "scroll to page + highlight paragraph" frontend behavior on top of Feature 2's payload (already carries page + snippet).
4. The corpus moat is a business decision (license vs. build on public sources), not a code task.

---

## 11. FEATURE — LoD Builder (List of Dates / chronology)

### 11.1 What it is
Auto-build a chronological List of Dates from one or more case documents: each entry = date + event summary + source document + page number + citation, sorted chronologically. Jurisphere's marquee litigation feature and our #1 parity gap.

### 11.2 Better than Jurisphere (design)
- **No hallucinated dates.** Dates are found *deterministically* with a multi-format regex over the source text (numeric `dd/mm/yyyy`, `yyyy-mm-dd`, written `15 October 2024` / `October 15, 2024` / `15th Oct 2024`, etc.). The LLM only summarizes the event around a real date and normalizes it — it never invents a date. (Same grounding discipline as Redline.)
- **ISO normalization** (`YYYY-MM-DD`) so a chronology built from mixed date formats sorts correctly.
- **Page-accurate citations** — a new per-chunk loader preserves `(page_number, text)`, so each date maps to the exact page it appears on.
- **Multi-document case files** — accepts N documents; every entry carries its own source filename + page.
- **LLM false-positive filtering** — the model marks non-event matches (e.g. "24/7", version numbers) so they're dropped.

### 11.3 Components
1. **DB model** `ListOfDates` (+ migration `0005`): id, tenant_id, created_by, name, document_ids (JSON), results (JSON list of `{date, iso_date, event, document_id, filename, page_number, snippet}`), status, timestamps.
2. **Loader** `load_document_chunks(db, tenant_id, doc_ids)` in `src/review/loader.py` — per-doc list of `(chunk_index, page_number, text, filename)`, tenant-scoped, ready-gated.
3. **Engine** `src/lod/engine.py`: `find_date_hits(chunks)` (regex + sentence context + page/doc attribution, capped) → `build_lod(llm, hits)` (batched JSON: is_event / iso_date / event) → chronological sort.
4. **API** `src/api/routers/lod.py`: create / list / get / delete (multi-doc); routed via `LLMTask.EXTRACT`; registered in `main.py`.
5. **Frontend** `ListOfDates.jsx` + nav + client (static-audited).

### 11.4 Acceptance criteria
- A synthetic case file with known dated events (mixed formats across two documents) yields a **chronologically sorted** list whose dates all actually appear in the source, each with the right event, source filename, and page.
- A non-event date token (e.g. "24/7 support") is filtered out.
- Cross-tenant docs rejected (404); not-ready rejected (400).
- Date regex + sentence-context extraction unit-tested independently of the LLM.

### 11.5 Audit
Unit-test `find_date_hits` (formats detected, page attribution, false-positive candidate). End-to-end on live stack: 2 synthetic docs with known events in different formats → build LoD → assert chronological order, correct dates/events/pages, false-positive dropped; isolation; cleanup.

### 11.6 Status — DONE, audited
- [x] Model `ListOfDates` + migration `0005` (applied; single head)
- [x] Per-chunk loader `load_document_chunks` (page-accurate)
- [x] Engine `src/lod/engine.py` (multi-format regex + sentence context + LLM summarize/normalize/filter + ISO chronological sort); date-detection unit-tested
- [x] API `src/api/routers/lod.py` (multi-doc create/list/get/delete, `extract` task) + registered
- [x] **Backend end-to-end audit — 15/15** on live stack: 2-doc case file, 4 mixed-format dates sorted chronologically with page-accurate citations, **no hallucinated dates**, false positives (`24/7`, `v2.10.1`) filtered; isolation; cleanup
- [x] Frontend `ListOfDates.jsx` (timeline UI) + nav + client (static-audited)

**LoD Builder is SOLID — and better than Jurisphere's:** dates are deterministically grounded (never hallucinated), ISO-normalized for correct cross-format sorting, page-accurate, and multi-document.

---

## 12. FEATURE — Word (.docx) export

### 12.1 What it is
"Download as Word" on every deliverable — Jurisphere has it on all outputs; we had none. One export service serializes each feature's result to a well-formatted `.docx`: Parallel Review → table, Redline → Change/Consequence table, List of Dates → chronology table, Translation → formatted text. Deterministic (no LLM), so fully verifiable now.

### 12.2 Components
1. **Service** `src/export/docx.py` — `review_to_docx`, `redline_to_docx`, `lod_to_docx`, `translation_to_docx` (each returns `bytes`), plus `docx_filename()` slug + `DOCX_MEDIA` constant. Uses `python-docx` (1.2.0, already a dependency).
2. **Endpoints** — `GET /{id}/export` on `review`, `redline`, `lod`, `translation` routers (viewer), returning the `.docx` as an attachment `Response`.
3. **Frontend** — a binary-download helper in `api/index.js` + "Export to Word" buttons on the four result views (static-audited).

### 12.3 Acceptance criteria
- Each builder produces a **valid `.docx`** (re-openable by python-docx) whose text/table cells contain the expected values (title, headers, a known data value).
- Export endpoints return `Content-Disposition: attachment` with the DOCX media type and a slugified filename, tenant-scoped (404 cross-tenant).
- Empty results still produce a valid (headers-only / title-only) document, no crash.

### 12.4 Audit
Unit-test all four builders (generate → re-open with python-docx → assert content). Verify endpoints registered; drive one full endpoint path against a directly-inserted row (no LLM) to prove wiring + tenant scoping.

### 12.5 Status — DONE, audited
- [x] Export service `src/export/docx.py` (review/redline/lod/translation builders + `docx_filename`/`DOCX_MEDIA`)
- [x] `GET /{id}/export` on all four routers (viewer, attachment Response) + registered
- [x] **Audit — builders 6/6** (valid docx + content + empty-safe + slug) **and endpoint path 5/5** (docx media, filename slug, content, cross-tenant 404)
- [x] Frontend: `downloadFile` helper + "Export to Word" buttons on all four result views (static-audited — icons/paths/imports verified)

**Word export is SOLID** — every feature's output is now a real `.docx` deliverable (Jurisphere parity on "Download as Word").

---

## 13. FEATURE — Drafting assistant

### 13.1 What it is
Instruction + matter documents → a complete, well-structured document (legal reply, notice, memo…), grounded in the provided sources with inline citations. Jurisphere's most demo-impressive feature (the KGMI reply: request → formal reply with parts, chronology, quantified damages, annexure of authorities, note-to-counsel). Uses the `draft` task (strongest model per routing).

### 13.2 Design (grounded, cited, "better")
- **Grounded:** the model drafts using ONLY the supplied source documents + the instruction; it is told not to invent facts unsupported by them.
- **Cited:** source documents are numbered `[1..N]` in context; the draft carries inline `[n]` markers and a trailing `SOURCES:` line that we parse into doc-level citations (number → filename), then strip. (Same discipline as citation-grounded research.)
- **`draft` task routing** — Groq now, a stronger model (Claude/GPT-4o/Gemini Pro) later via env with no code change.
- **Word export built in** — reuses the export service (`draft_to_docx`), so a draft is a real `.docx` deliverable immediately.
- Documents optional: with sources → grounded+cited; without → drafts from the instruction alone.

### 13.3 Components
1. **DB model** `Draft` (+ migration `0006`): id, tenant_id, created_by, name, instruction, document_ids (JSON), content (Text, markdown), citations (JSON), status, timestamps.
2. **Engine** `src/drafting/engine.py`: `generate_draft(llm, instruction, docs)` → `{content, citations}` (numbered sources, strong prompt, SOURCES parse+strip, retry).
3. **Export** `draft_to_docx` added to `src/export/docx.py` (headings + paragraphs from the markdown).
4. **API** `src/api/routers/drafting.py`: create / list / get / delete / export; `draft` task; registered.
5. **Frontend** `Drafting.jsx` + nav + client (static-audited).

### 13.4 Acceptance criteria
- A source demand-notice doc + "draft a reply disputing the 18% interest" → a substantial draft that references the source's concrete facts (amount, 18% interest, parties), cites the source document, and reads as a formal reply. `SOURCES:` line stripped from the displayed content.
- No fabrication of a fact absent from source + instruction (spot-checked: a value not present shouldn't appear).
- Cross-tenant docs rejected (404); not-ready rejected (400).
- Draft exports to a valid `.docx`.

### 13.5 Audit
End-to-end on the live stack: synthetic demand-notice doc with known facts → draft a grounded reply → assert it cites the source, includes the key facts, is non-trivial, SOURCES stripped; export to docx opens with content; isolation; cleanup.

### 13.6 Status — DONE, audited
- [x] Model `Draft` + migration `0006` (applied; single head)
- [x] Engine `src/drafting/engine.py` (numbered sources + strong `draft`-task prompt + grounded `[n]` citations + SOURCES parse/strip + retry)
- [x] `draft_to_docx` in the export service (markdown headings + paragraphs)
- [x] API `src/api/routers/drafting.py` (create/list/get/delete/**export**) + registered
- [x] **Backend end-to-end audit — 15/15** on live stack: grounded reply used the source's real facts (Rs 2,86,848, 18% interest, both parties), cited the source doc, no fabrication, SOURCES stripped, exports to valid `.docx`; instruction-only mode; isolation; cleanup
- [x] Frontend `Drafting.jsx` (markdown render + Sources chips + Export to Word) + nav + client (static-audited)

**Drafting assistant is SOLID** — Jurisphere's most demo-impressive feature, matched with grounded, cited, exportable output on the `draft` task (upgradable to a stronger model via env, no code change).

---

## 14. SECURITY — Phase-0 hardening (pilot blockers)

Code-level fixes from `jurisphere-vs-duckvault.md` §7 Phase-0 that block an external pilot. (Ops items — G2 secret rotation, G4 TLS — are deployment tasks noted there, not code.)

### 14.1 Fixes
- **G7 — Stream-replay IDOR (confirmed real).** The Redis buffer key `stream:{query_id}` had no tenant binding; any viewer with another tenant's `query_id` (leaked via the `X-Query-Id` header) could replay their answer+citations. Fix: namespace the key `stream:{tenant_id}:{query_id}` in `cache.py` and pass `tenant_id` from both call sites in `query.py` — a cross-tenant `query_id` now resolves to an empty buffer.
- **G5 — Open admin-minting registration.** `POST /auth/register` was unauthenticated and created an `org_admin` for anyone. Fix: gate behind `allow_open_registration` (default **False**) + optional `registration_allowed_domains` allowlist; blocked registrations return 403.
- **G1 — Default infra credentials.** Fail-fast `Settings` validator that refuses to boot on `minioadmin` / `rag:rag` / empty Qdrant key **when `debug` is False** (local dev with `debug=true` is unaffected). Mirrors the existing `SECRET_KEY` validator.
- **G6 (partial) — Failed-login audit.** `/auth/login` now writes a `user_login_failed` audit record for a wrong-password attempt on an existing account (brute-force signal).

### 14.2 Acceptance criteria
- After G7: events pushed under tenant A are replayable by A, and return **empty** for tenant B (cross-tenant isolation on the replay buffer).
- After G5: with the flag off, registration returns 403; with an allowlist, only listed domains succeed; with the flag on, open registration works.
- After G1: with `debug=False` + default creds → boot raises; with `debug=True` (dev) or non-default creds → boots fine.
- After G6: a wrong-password login on a real account writes a `user_login_failed` audit row (email only, no secret).

### 14.3 Status — DONE, audited (16/16)
- [x] **G7 IDOR fix** — `cache.py` stream key namespaced by tenant; both `query.py` call sites pass `tenant_id`. Audited on live Redis: owner replays, cross-tenant returns empty.
- [x] **G5 registration gate** — `allow_open_registration` (default False) + `registration_allowed_domains` in `config.py`; `_registration_allowed()` gate in `auth_router`; 403 when blocked. Documented in `.env.example`.
- [x] **G1 infra-cred validator** — `Settings._reject_default_infra_creds` fails fast on minioadmin / rag:rag / empty Qdrant key when `debug=False`; dev (`debug=true`) unaffected.
- [x] **G6 failed-login audit** — wrong password on a real account writes a `user_login_failed` row (email only, no secret); unknown emails not logged (no enumeration).

**Behavior change to note:** self-serve registration is now OFF by default. For local dev / self-serve signup set `ALLOW_OPEN_REGISTRATION=true`.

Remaining security roadmap (deferred, from `jurisphere-vs-duckvault.md` §7): ops items G2 (secret rotation) / G3 (DEBUG=false in prod) / G4 (TLS); Phase-1 G6-throttle / G8 quotas / G9 malware-scan; Phase-2 SSO+MFA / at-rest encryption / JWT hardening.

---

## 15. SECURITY — Phase-1 hardening (untrusted entry points)

Next security tranche from `jurisphere-vs-duckvault.md` §7 — hardening the unauthenticated/entry surfaces, all verifiable now.

### 15.1 Fixes
- **G20 — Rate limiter fails open.** `rate_limit_check` previously let a Redis outage 500 the `/query` path. Now it catches Redis errors and **fails open** (allows the request, logs a warning) — availability over strict limiting.
- **G6 — Auth-endpoint throttling.** `/auth/login` and `/auth/register` are unauthenticated, so the per-tenant limiter never covered them (brute-force/credential-stuffing unmitigated). Add a **per-IP** sliding-window throttle (`auth_rate_limit_per_minute`, default 10) → 429 + `Retry-After` when exceeded. Honors a single `X-Forwarded-For` hop.
- **G9 — Magic-byte upload validation.** Uploads were trusted by extension + client `content_type` only. Add a content sniff (`filetype`) that rejects a file whose real bytes don't match its declared type (a renamed `.exe`/script masquerading as `.pdf`), before it ever reaches parsing.

### 15.2 Acceptance criteria
- G20: with Redis unreachable, `rate_limit_check` returns `(True, 0)` (allow) instead of raising.
- G6: the (N+1)th auth attempt from one IP within a minute returns 429; a different IP is unaffected.
- G9: PDF/PNG/DOCX bytes matching their type pass; an exe/plain-text/random payload declared as `.pdf` is rejected; sniff logic unit-tested.

### 15.3 Status — DONE, audited (11/11)
- [x] **G20** — `rate_limit_check` fails open on Redis error (`cache.py`); verified with a broken client.
- [x] **G6** — per-IP throttle on `/auth/login` + `/auth/register` (`auth_rate_limit_per_minute`, default 10); verified 11th attempt → 429, other IPs unaffected, `X-Forwarded-For` honored.
- [x] **G9** — magic-byte upload validation (`src/ingestion/content_scan.py`) wired into the upload handler; verified real PDF/PNG/DOCX pass while EXE / plain-text / type-mismatch are rejected.

Remaining security roadmap: G8 (enforce the modeled QPD/concurrency/ingestion + demo quotas — currently dead config); Phase-2 (SSO+MFA, at-rest/field encryption, JWT `iat`/`nbf`/`aud` + revocation, complete audit coverage, password policy); Phase-3 (SOC2/ISO program, non-root Dockerfile, sanitize client errors). Ops: rotate exposed Groq key, DEBUG=false in prod, TLS between services.

---

## 16. SECURITY — G8 quota enforcement (dead config → enforced)

The audit flagged per-tenant/day, demo, and document quotas as *modeled but never enforced* (e.g. `incr_demo_queries` had zero callers). This wires the daily query quota and the demo document cap.

### 16.1 Fixes
- **Daily query quota (QPD).** `cache.incr_daily_queries` (new) + `_enforce_daily_quota` in the query router: real (non-cached) queries increment a 24h Redis counter; over the cap → 429. Demo tenants use the stricter `rate_limit_demo_qpd` (30) via the previously-unused `incr_demo_queries`; others use `rate_limit_default_qpd` (1000). Cache hits are free (checked first).
- **Demo document cap.** Uploads by a `demo`-role user are capped at `demo_max_documents` (5) rather than the tenant's general `quota_documents`.

### 16.2 Acceptance criteria
- The daily counter increments per real query; the (limit+1)th query in a day → 429; demo vs. non-demo use the correct counter + cap; cache hits don't count.
- A demo tenant is blocked at 5 documents; a normal tenant uses its general quota.

### 16.3 Status — DONE, audited (8/8)
- [x] `cache.incr_daily_queries` + `_enforce_daily_quota` wired into `/query/stream` (non-cached only)
- [x] demo document cap (`documents.py` upload — `demo_max_documents` for demo role)
- [x] Audit: counter increments; default quota 429 at limit+1; demo quota uses the demo counter + stricter cap; demo doc cap wired

Deferred (bigger): per-tenant `RateLimitConfig` DB overrides + `max_concurrent_queries` in-flight tracking. Concept is now enforced via settings defaults; per-tenant tuning layers on next.

Deferred (bigger): per-tenant `RateLimitConfig` overrides (QPD/ingestion/hr/concurrency) read from the DB row, and `max_concurrent_queries` (in-flight tracking). Current enforcement uses settings defaults — the concept is no longer dead; per-tenant tuning layers on next.

---

## 17. SECURITY — Phase-2: JWT hardening (G14) + password policy (G15)

### 17.1 Fixes
- **G14 — JWT hardening + revocation.** Tokens now carry `iat`, `nbf`, `exp`, `iss`, `aud`, and a unique `jti`; `decode_token` verifies issuer + audience (and exp/nbf) everywhere (`auth.py`, and the rate-limit middleware). A Redis-backed **jti denylist** + `POST /auth/logout` revoke a token so it can't be reused; `get_current_user` rejects revoked tokens (fails open on a Redis outage). Legacy/forged tokens missing `iss`/`aud` are now rejected.
- **G15 — Password policy.** `validate_password` enforces a minimum length (`min_password_length`, default 8) and rejects passwords longer than bcrypt's 72-byte limit (beyond which bcrypt silently truncates). Enforced in `/auth/register` → 400 on violation.

### 17.2 Acceptance criteria
- A minted token decodes with iss/aud/jti/iat/nbf/exp; a token lacking iss/aud is rejected.
- After `revoke_token`/logout, `get_current_user` on that token returns 401; a different token is unaffected.
- Rate-limit middleware still extracts tenant_id from the new tokens.
- `validate_password` rejects too-short and >72-byte passwords, accepts valid ones; register returns 400 on a weak password.

### 17.3 Status — DONE, audited (12/12)
- [x] G14 — token claims (iat/nbf/iss/aud/jti), `decode_token` verifies iss+aud (auth.py + middleware), jti denylist + `POST /auth/logout` revocation (fail-open), legacy tokens rejected. Frontend logout now calls the revoke endpoint (best-effort).
- [x] G15 — `validate_password` (min length + 72-byte bcrypt guard) enforced in register (400 on violation).
- Audit 12/12: claims present+verified, legacy rejected, revoked→401, other tokens unaffected, middleware reads new tokens, password policy + register 400.

**Behavior change:** existing tokens (issued before this change) lack `iss`/`aud` and are now rejected → users must re-login. Deferred Phase-2: SSO/MFA, encryption-at-rest, full audit-action coverage (G13).

---

## 18. SECURITY — G13 audit coverage (+ G15 completeness)

### 18.1 Fixes
- **G13 — write the missing audit actions.** `document_upload` and `document_delete` (in `documents.py`) and `tenant_create` (in `auth_router` register) are now written — previously in the enum but never emitted. Each row captures **caller IP + user-agent** (`_req_meta`, honoring `X-Forwarded-For`). (`user_create`/`role_change` were already written by admin; `user_delete`/`tenant_delete` have no endpoint yet, so no code path.)
- **G15 completeness** — the password policy (`validate_password`) now also applies to admin-created users (`admin.py`), not just self-registration.

### 18.2 Acceptance criteria
- Registering a tenant writes a `tenant_create` audit row with tenant_name/domain/ip/user_agent.
- Deleting a document writes a `document_delete` row (filename + ip/ua); uploading writes `document_upload`.
- `_req_meta` extracts the real client IP (incl. behind `X-Forwarded-For`).
- Admin creating a user with a weak password → 400.

### 18.3 Status — DONE, audited (8/8)
- [x] `document_upload` + `document_delete` audit rows (documents.py) with IP + user-agent; delete verified live (row written, doc removed).
- [x] `tenant_create` audit on register (auth_router) — verified with ip/ua/domain in metadata.
- [x] G15: admin-created users now pass `validate_password` (400 on weak).
- [x] `_req_meta` IP extraction incl. `X-Forwarded-For` verified.

Note: `user_delete`/`tenant_delete` remain unemitted only because no such endpoints exist yet. Remaining audit hardening (deferred): IP/UA on login/query rows too, and WORM/append-only tamper-evidence.

---

## 19. SECURITY — G11 at-rest field encryption

### 19.1 What & how
Sensitive content columns are now encrypted at rest via a transparent SQLAlchemy `TypeDecorator` (`src/db/crypto.py`, Fernet/AES). Encryption happens on write, decryption on read — routers/engines are unchanged. Applied to the highest-volume plaintext content: **`Chunk.text`** (all document text), **`Translation.result`**, **`Draft.content`**. The DB column stays `TEXT` (encrypted blob prefixed `enc::`), so **no migration** is needed.

Safety: legacy plaintext rows (no prefix) read back untouched; an undecryptable value (e.g. after key rotation) is returned raw rather than crashing. Key comes from `field_encryption_key`, or is derived from `SECRET_KEY` if unset.

### 19.2 Acceptance criteria
- `encrypt_str`→`decrypt_str` round-trips; legacy plaintext passes through; undecryptable value returns raw.
- A `Chunk` written via the ORM is stored as `enc::…` ciphertext at rest (verified by a raw SQL read) and decrypts transparently on ORM read (including `select(Chunk.text)`, the loader path).
- `Translation.result` and `Draft.content` use the encrypted type.

### 19.3 Scope / deferred
Covered: the three high-value Text columns. **Deferred:** JSON `results` columns (ParallelReview/Redline/LoD — encrypting them means a TEXT type migration), the Qdrant vector payload (`text_preview` — needed plaintext for retrieval display; separate design), raw object-store files (bucket/disk encryption is an ops/KMS task), and audit-log PII. Also: key rotation strategy + KMS-managed keys are an ops follow-up.

### 19.4 Status — DONE, audited (9/9)
- [x] `src/db/crypto.py` — Fernet cipher + `EncryptedText` TypeDecorator; key from `field_encryption_key` or derived from `SECRET_KEY`.
- [x] Applied to `Chunk.text`, `Translation.result`, `Draft.content` (no migration — column stays TEXT).
- [x] Audit: roundtrip / legacy-passthrough / undecryptable-fallback; **live DB shows ciphertext at rest, plaintext absent, transparent decrypt on `select(Chunk.text)`**.

**Note:** existing rows written before this change remain plaintext (read fine via fallback); a one-off re-save/backfill would encrypt them. Qdrant `text_preview`, Redis query cache, and audit-log PII remain plaintext (see §19.3).

---

## 20. SECURITY — MFA / TOTP two-factor (G10)

### 20.1 What & how
Time-based OTP two-factor auth. `src/api/totp.py` implements RFC 6238 (stdlib only — no new dependency; SHA1/6-digit/30s, Authenticator/Authy-compatible). `User` gains `mfa_secret` (stored via the G11 `EncryptedText` type — encrypted at rest) and `mfa_enabled` (migration `0007`).

Flow: `POST /auth/mfa/setup` (authed) generates a secret + `otpauth://` URI for QR enrollment → `POST /auth/mfa/verify` confirms a code and flips `mfa_enabled` on → login then requires a valid `mfa_code` (distinct 401 "MFA code required" so the client can prompt) → `POST /auth/mfa/disable` (with a valid code) turns it off.

### 20.2 Acceptance criteria
- TOTP matches the RFC 6238 reference vectors; verify tolerates ±1 period; non-numeric/expired codes fail.
- setup returns secret + otpauth URI and stores the secret **encrypted at rest**; verify with a correct code enables MFA, a wrong code 400s.
- With MFA on: login without a code → 401 "MFA code required"; correct code → token; wrong code → 401 (+ `user_login_failed` audit). Without MFA: login unchanged.
- disable with a valid code clears the secret.

### 20.3 Status — DONE, audited (18/18)
- [x] `src/api/totp.py` — RFC-6238 TOTP (stdlib), matches reference vectors; ±1 window; rejects non-numeric/expired.
- [x] `User.mfa_secret` (EncryptedText) + `mfa_enabled` + migration `0007` (applied; single head).
- [x] `/auth/mfa/setup` `/verify` `/disable` + login `mfa_code` gate; failed MFA writes `user_login_failed`.
- [x] Audit 18/18 on live stack: enrollment, secret encrypted at rest, verify enable, login gate (no-code→401 / correct→token / wrong→401), disable.

**Frontend follow-up (not built — build-blocked):** a login `mfa_code` field + an enrollment screen (QR from the otpauth URI). The API is ready; the Login page is under active edit by you, so I left it alone.

Note: this is TOTP MFA. Full SSO (SAML/OIDC) remains a separate, larger item — `hashed_password` is already nullable to accommodate SSO-only users later.

---

## 6. Features 5–7 — specs to be expanded when reached
Each remaining feature gets a §-section like Feature 1 (components / acceptance / audit) at the moment we start it, so specs stay honest to the code that exists then rather than guessed up front.
