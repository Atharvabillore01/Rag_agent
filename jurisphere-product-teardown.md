# Jurisphere — Complete Product Teardown (from their live API)

**Last updated:** 2026-07-26
**Source:** their production OpenAPI spec (`https://api.jurisphere.ai/openapi.json` — **213 paths, 310 schemas**), parsed field-by-field. This is the full reverse-engineered product: every feature, its data model, the platform capabilities, and a map to what DuckVault has.

---

## 1. The core abstraction — "Matters"

Everything a user creates is a **Matter** (`MatterSchema`): `id, name, type, updated_at, created_by_user_name/email, project_id, user_role`. One generic table + a `type` discriminator, so list / rename / delete / feedback / analytics / assignments / sharing work uniformly across every feature. Matters live inside **projects** (a workspace/folder grouping with roles).

### The 13 matter types (= their complete feature catalog)
`research` · `document-review` · `timeline` · `translation` · `redline-analysis` · `company-profile` · `document-table` · `word-add-in` · `outlook-add-in` · `assistant` · `review-playbooks` · `multi-step-workflow` · `circle-ups`

**DuckVault today models each feature as its own table.** Adopting a unified matter model is the single biggest architectural refactor to reach their generality (shared list/share/assign/analytics for free).

---

## 2. Feature-by-feature (with real data model + DuckVault status)

| Jurisphere feature (matter type) | What it does (from the schema) | DuckVault |
|---|---|---|
| **document-table** | Their Parallel Review. `AskPayload{query, questions[{question, table_header}], attached_file_ids, project_id, workflow_id}` → `DocumentTableMatter{questions, attached_file_ids, answers[IndividualAnswer], is_complete, processing_status}`. Driven by **pre-built workflow templates** (`DocumentTableWorkflowSchema{title, tags, priority, recommended_rank, source, is_word_add_in_enabled, details}`) + a `/document-table/questions` library. Has a **streaming chat** over the table. | ✅ Built (Parallel Review). Missing: **workflow-template library**, per-matter chat, NL→columns from a free-text `query`. |
| **research** | `ResearchMatter{chats[ResearchChat], is_archived}` — a multi-turn research matter (agentic, grounded on their corpus). | ✅ Agentic research built. Missing: multi-chat-per-matter, their corpus, multi-sub-agent fan-out. |
| **document-review** | `DocumentReviewMatter{file_ids, content:DocumentReviewMatterContent}` — "talk to documents" / consent tracker over a doc set. | ✅ Chat/query built; ◑ no dedicated consent-tracker skill. |
| **timeline** | Their LoD. `/timeline` (start job) → `TimelineMatter`; **editable rows** (`EditTimelineRowPayload{row_id, category}`), **citation-click tracking**, and a **timeline chat** (SSE). | ✅ Built (LoD). Missing: editable-row categories, citation-click analytics, per-timeline chat. |
| **redline-analysis** | Change/consequence diff. | ✅ Built. |
| **translation** | Doc translation. | ✅ Built (text); vision-OCR pending a key. |
| **company-profile** | **MCA integration.** `CompanyProfileMatter{cin, documents_zip_signed_url, detailed_report_excel_signed_url, include_detailed_report, version, failed_documents[FailedMCADocument]}` + `/company-profile/search` + `/get-company-master-data`. Pulls a company's filings from India's MCA, bundles a ZIP + Excel report. Metered (₹200/company). | ❌ Missing — external MCA data integration. |
| **word-add-in** / **outlook-add-in** | Microsoft Office + Outlook add-ins (Outlook via **MS Graph** identity in `SettingsSchema.outlook_add_in_graph_identity`). Draft/redline inside Word; triage/ingest email in Outlook. | ❌ Missing (both add-ins). |
| **assistant** | A general AI assistant matter (metered separately, `AssistantUsageForFeature`). | ✅ Chat built. |
| **review-playbooks** | Review a contract **against a standard playbook/template**. | ◑ Redline engine exists; playbook variant noted, not built. |
| **multi-step-workflow** | Chained multi-step automations across features. | ❌ Missing. |
| **circle-ups** | Collaboration/meeting/summary surface (grouping matters or people). | ❌ Missing. |

---

## 3. Platform capabilities (beyond the features)

- **Knowledge Bank** (`/knowledge-bank/*`) — an **org-wide shared corpus**, ingested as archives with rich progress (`KnowledgeBankStatusResponse{status, archive_name, total_size_bytes, files_total/processed/indexed, folders_count, progress_percent, need_attention_count, failure_reason}`) + retry. Separate from per-matter docs — this is the firm's institutional memory / RAG base. ❌ DuckVault missing.
- **CLM (Contract Lifecycle Management)** (`/clm/*`) — extract & track `documents`, `entities`, `obligations`, `transactions` across a contract portfolio (each a paginated `{items, total}`). ❌ Missing.
- **Assignments & collaboration** (`/assignments`, `/comments`, `/activity`) — `AssignmentResponse{title, description, status, due_date, source_type, source_ref, project, creator, assignee, comment_count, updated_by}` + threaded comments + activity feed. Assign a matter to a colleague with a due date. ❌ Missing.
- **Memory** (`/users/me/memories`, `/organizations/me/memory`) — `UserMemory{title, description, category, auto_created}` where `MemoryCategory ∈ {persona, format_and_style, processing_and_commands, other}`. The AI **remembers your writing persona, formatting preferences, and standing commands** (auto-created + manual). ❌ Missing (we have model-level memory only, not product memory).
- **Tasks** (`/tasks`, `/tasks/{id}/retry`) — async job tracking (`TaskSchema{category, status, started_at, completed_at, details}`), backed by Temporal. ◑ We have `IngestionJob`; no unified task API/retry.
- **Auto-folderise** (`/library/auto-folderise*`) — AI suggests + applies a folder structure. ❌ Missing (we have folders, not the organizer).
- **Usage metering** (`OrganizationUsageSchema`) — per-feature quotas/usage for **all 10 features** + per-user citation usage. This is the billing spine. ◑ We model `RateLimitConfig`/`DemoQuota` but don't enforce.
- **Billing** — Razorpay + LemonSqueezy: **day-pass, monthly subscription, per-feature top-ups**. ❌ Missing.
- **Add-ins & integrations** — Word + Outlook (MS Graph); Google Docs ingest (`ContentType`), download-from-URL. ❌ Missing.
- **Compliance** — `/consents` (terms/privacy/marketing/product_updates, versioned source forms), announcements, referrals, in-app support tickets. ◑ We have audit; no consent capture.
- **I/O helpers** — `/transcribe` (STT ✅ have), `/text-to-speech` + voices ❌, `/convert-to-excel` ❌.
- **Platform-admin console** (`X-Jurisphere-Admin-Key`, `/console/*`) — cross-org admin. ◑ We have org admin, not platform console.

---

## 4. Ingestion — exact file support & upload

- **Accepted `ContentType`:** PDF, DOCX, DOC, **Google Docs**, XLSX, XLS, CSV, **Outlook `.msg` / `.pst`**, **rfc822 email**, HTML, **ZIP**, TXT, JPEG/PNG, JSON, Markdown. (Email archives + ZIP = built for **legal discovery / e-discovery**, not just single docs.)
- **Upload:** presigned single-part (`/upload-url`) **and** full **S3 multipart** (`init/sign-part/complete/abort`) — client → S3 direct; processing decoupled via `/process` + Temporal tasks. (This is the "unlimited upload" mechanic.)
- DuckVault: ingests PDF/DOCX/PPTX/images; **missing**: email (.msg/.pst), ZIP, XLSX/CSV, Google Docs; and upload goes through the API (no direct-to-S3 multipart yet).

---

## 5. Auth & infra (confirmed)
- **Clerk** for identity (`/webhooks/clerk`, HTTPBearer) — managed SSO/MFA/orgs.
- **Temporal** for durable async workflows.
- **FastAPI** + **S3 multipart** + **SSE** streaming + **Razorpay/LemonSqueezy** + **Typeform** onboarding.
- `/health` + `/readiness` (k8s-style probes).

---

## 6. DuckVault gap map (what "understanding everything" implies we still lack)

**Have (parity or better):** document-table/Parallel Review, research, document-review/chat, timeline/LoD, redline, translation, assistant, drafting, Word export, contentions, PII redaction, folders, skills, voice/transcribe, multi-model routing, tenant isolation + Phase-0 security + MFA.

**Missing — product surface:**
1. **Unified matter + project model** (architectural refactor; unlocks the rest cheaply).
2. **Knowledge Bank** (org shared corpus).
3. **CLM** (entities/obligations/transactions).
4. **Assignments / comments / activity** (collaboration).
5. **Memory** (persona/style/commands personalization).
6. **Company Profile / MCA** + external data integrations.
7. **Word & Outlook add-ins** (+ MS Graph).
8. **Workflow-template library** for document-table; **review-playbooks**; **multi-step-workflow**; **circle-ups**.
9. **Auto-folderise**, **TTS**, **convert-to-Excel**.
10. **Usage metering enforcement + billing** (Razorpay/Stripe, day-pass/subscription/top-ups).
11. **Broader ingestion** (email `.pst`/`.msg`, ZIP, XLSX/CSV, Google Docs) + **direct-to-S3 multipart**.
12. **Consent capture**, platform-admin console, announcements/referrals/support.

**Missing — infra/enterprise:** managed IdP or SSO/OIDC, Temporal-grade durable workflows, encryption-at-rest, TLS everywhere, SOC2/ISO, observability stack, k8s/IaC/CI-CD.

**The moat (non-code):** their ~15M-doc Indian legal corpus + fine-tunes + knowledge graph.

---

## 7. Verdict
Yes — this is the whole product. Jurisphere = a **project/matter workspace** wrapping ~13 AI document features, a **shared Knowledge Bank + CLM**, a **collaboration layer** (assignments/comments), **personalization memory**, **usage metering + billing**, **Office/Outlook add-ins + MCA/Google integrations**, on **Clerk + Temporal + S3-multipart + FastAPI**. DuckVault matches the **AI-feature core**; the deltas are mostly **workspace/collaboration/billing/integration surface** and **enterprise infra** — all standard engineering — plus the **legal-corpus moat**, which is a business decision.
