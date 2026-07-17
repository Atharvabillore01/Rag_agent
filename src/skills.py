"""Domain skill library — pre-built workflow templates (feature-implementation-plan §25).

A "skill" is a named, domain-scoped template that pre-fills one of the platform's
features: e.g. Legal → "Change-of-Control Tracker" pre-loads Parallel Review with
the relevant columns; CA → "Reply to Tax Notice" pre-loads Drafting with a tuned
instruction. This is the demo's "In-Built Skills" surface and the concrete payload
of a domain pack (see :mod:`src.domains`).

Design mirrors the domain registry: skills live in this one file as plain data, so
onboarding a vertical or adding a template is an edit here — not code or a schema
migration. Each skill's ``preset`` is validated against its ``feature`` by the
audit; keep them consistent when adding entries.
"""

from __future__ import annotations

from src.domains import DEFAULT_DOMAIN, normalize_domain

# Features a skill can pre-fill. Kept as a set so the audit (and any future
# validation) can reject a skill that points at a feature we don't ship.
FEATURES = {"parallel_review", "drafting", "lod", "redline", "translation", "contentions", "pii"}


def _review(*pairs: tuple[str, str]) -> dict:
    """Build a parallel_review preset from (header, question) pairs."""
    return {"questions": [{"header": h, "question": q} for h, q in pairs]}


# id -> skill. ``domain`` is the vertical it belongs to; "generic" skills are
# offered to every tenant on top of their own vertical's skills.
SKILLS: list[dict] = [
    # ── Generic (available to all tenants) ───────────────────────────────────
    {
        "id": "summarize-key-facts",
        "domain": "generic",
        "name": "Summarize & Key Facts",
        "description": "Pull a summary plus the key dates, parties and amounts from each selected document.",
        "feature": "parallel_review",
        "preset": _review(
            ("Summary", "Give a concise summary of this document."),
            ("Parties", "Who are the parties or entities involved?"),
            ("Key Dates", "What are the important dates and deadlines?"),
            ("Key Amounts", "What monetary amounts or figures are stated?"),
        ),
    },
    {
        "id": "draft-document",
        "domain": "generic",
        "name": "Draft a Document",
        "description": "Draft a new document grounded in the selected files.",
        "feature": "drafting",
        "preset": {"instruction": "Draft a clear, well-structured document grounded in the selected source files. State any assumptions explicitly."},
    },
    {
        "id": "build-chronology",
        "domain": "generic",
        "name": "Build a Chronology",
        "description": "Assemble a source-cited, dated chronology of events from the selected files.",
        "feature": "lod",
        "preset": {},
    },
    {
        "id": "translate-document",
        "domain": "generic",
        "name": "Translate a Document",
        "description": "Translate a document into another language, segment by segment.",
        "feature": "translation",
        "preset": {"target_language": "English"},
    },
    {
        "id": "scan-sensitive-data",
        "domain": "generic",
        "name": "Scan for Sensitive Data",
        "description": "Detect PII (Aadhaar, PAN, GSTIN, cards, email, phone) and produce a redacted copy.",
        "feature": "pii",
        "preset": {},
    },

    # ── Legal ─────────────────────────────────────────────────────────────────
    {
        "id": "change-of-control-tracker",
        "domain": "legal",
        "name": "Change-of-Control Tracker",
        "description": "Extract change-of-control clauses, consent requirements and termination triggers across a set of agreements.",
        "feature": "parallel_review",
        "preset": _review(
            ("Change of Control", "What does the change-of-control clause say?"),
            ("Consent Required", "Is prior consent required on a change of control, and from whom?"),
            ("Notice Period", "What notice period applies to a change of control?"),
            ("Termination Right", "Does a change of control give any party a right to terminate?"),
        ),
    },
    {
        "id": "loan-terms-covenants",
        "domain": "legal",
        "name": "Loan Terms & Covenants",
        "description": "Compare principal, rate, due dates, events of default and covenants across loan agreements.",
        "feature": "parallel_review",
        "preset": _review(
            ("Principal Amount", "What is the principal loan amount?"),
            ("Interest Rate", "What is the interest rate and how is it computed?"),
            ("Next Due Date", "What is the next payment or maturity date?"),
            ("Events of Default", "What are the events of default?"),
            ("Negative Covenants", "What negative covenants restrict the borrower?"),
        ),
    },
    {
        "id": "exhibit-analysis",
        "domain": "legal",
        "name": "Exhibit Analysis",
        "description": "For each exhibit: what it is, why it matters, and which fact it supports.",
        "feature": "parallel_review",
        "preset": _review(
            ("Description", "What is this document and what type of exhibit is it?"),
            ("Relevance", "Why is this document relevant to the dispute?"),
            ("Supports", "Which fact or allegation does this document support or rebut?"),
            ("Date", "What is the date of this document?"),
        ),
    },
    {
        "id": "reply-to-demand-notice",
        "domain": "legal",
        "name": "Reply to Demand Notice",
        "description": "Draft a formal reply to a demand notice, rebutting each claim and setting out any counterclaim.",
        "feature": "drafting",
        "preset": {"instruction": "Draft a formal, without-prejudice reply to the demand notice in the selected documents. Address and rebut each claim in turn, cite the relevant provisions, and set out any counterclaim or set-off available to our client."},
    },
    {
        "id": "list-of-dates",
        "domain": "legal",
        "name": "List of Dates",
        "description": "Build a litigation chronology (List of Dates & Events) with source citations.",
        "feature": "lod",
        "preset": {},
    },
    {
        "id": "compare-contentions",
        "domain": "legal",
        "name": "Compare Contentions",
        "description": "Derive the disputed issues across pleadings and compare each party's stance (admits / denies) side by side.",
        "feature": "contentions",
        "preset": {},
    },

    # ── Chartered Accountancy / Tax ──────────────────────────────────────────
    {
        "id": "reply-to-tax-notice",
        "domain": "ca",
        "name": "Reply to Tax Notice",
        "description": "Draft a reply to an Income-Tax or GST notice, addressing each point and citing the relevant sections.",
        "feature": "drafting",
        "preset": {"instruction": "Draft a reply to the tax notice in the selected documents. Address each point raised, cite the relevant Income Tax Act / GST provisions, and set out the remedies and reliefs available to the assessee."},
    },
    {
        "id": "invoice-gst-extraction",
        "domain": "ca",
        "name": "Invoice / GST Extraction",
        "description": "Extract GSTIN, invoice number and date, taxable value and tax across a batch of invoices.",
        "feature": "parallel_review",
        "preset": _review(
            ("GSTIN", "What is the supplier GSTIN?"),
            ("Invoice No. & Date", "What is the invoice number and date?"),
            ("Taxable Value", "What is the taxable value before tax?"),
            ("Tax Amount", "What is the total tax (CGST / SGST / IGST)?"),
        ),
    },
    {
        "id": "financial-covenant-review",
        "domain": "ca",
        "name": "Financial Covenant Review",
        "description": "Extract financial ratios and covenant thresholds (DSCR, current ratio, leverage) across facility agreements.",
        "feature": "parallel_review",
        "preset": _review(
            ("Covenants", "What financial covenants are required?"),
            ("Thresholds", "What are the required ratio thresholds (e.g. DSCR, current ratio, leverage)?"),
            ("Testing Frequency", "How often are the covenants tested?"),
            ("Consequence of Breach", "What happens on a covenant breach?"),
        ),
    },
]


def get_skills_for_domain(domain: str | None) -> list[dict]:
    """Return the skills offered to a tenant on the given ``domain``.

    That vertical's skills plus the always-on "generic" skills. Unknown or empty
    domains coerce to :data:`~src.domains.DEFAULT_DOMAIN` (generic only), matching
    :func:`src.domains.normalize_domain`. Generic skills are listed last so a
    vertical's own templates lead.
    """
    key = normalize_domain(domain)
    specific = [s for s in SKILLS if s["domain"] == key and key != DEFAULT_DOMAIN]
    generic = [s for s in SKILLS if s["domain"] == DEFAULT_DOMAIN]
    return specific + generic
