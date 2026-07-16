"""Parallel Review endpoints (feature-implementation-plan §3).

Create and view "N documents × M questions → answers table" runs. Answers are
produced only from the selected documents (see src/review/loader + engine); no
external retrieval and no cross-tenant data.
"""

import copy
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.api.auth import require_editor, require_viewer
from src.db.models import ParallelReview, Tenant, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, docx_filename, review_to_docx
from src.providers.factory import LLMTask, get_tenant_task_llm
from src.review.engine import ReviewQuestion, run_review, slugify_key
from src.review.loader import load_document_texts

router = APIRouter(prefix="/review", tags=["review"])
logger = logging.getLogger(__name__)

# Bounds keep a single review's cost predictable (worst case docs × questions
# LLM calls-worth of work). Raise later per-tier if needed.
MAX_DOCUMENTS = 25
MAX_QUESTIONS = 15


# ── Schemas ───────────────────────────────────────────────────────────────────

class QuestionIn(BaseModel):
    header: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=2000)


class CreateReviewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    document_ids: list[str] = Field(min_length=1)
    questions: list[QuestionIn] = Field(min_length=1)


class AddColumnsRequest(BaseModel):
    questions: list[QuestionIn] = Field(min_length=1)


class ReviewSummary(BaseModel):
    id: str
    name: str
    status: str
    document_count: int
    question_count: int
    created_at: str


class ReviewDetail(BaseModel):
    id: str
    name: str
    status: str
    document_ids: list[str]
    questions: list[dict]
    results: dict | None
    created_at: str
    updated_at: str


# ── Helpers ─────────────────────────────────────────────────────────────────

def _build_questions(items: list[QuestionIn], existing_keys: set[str]) -> list[ReviewQuestion]:
    """Turn incoming {header, question} into ReviewQuestion with unique keys.

    Keys are slugified from headers; collisions (including with already-stored
    columns) get a numeric suffix so every column maps to a distinct JSON key.
    """
    out: list[ReviewQuestion] = []
    seen = set(existing_keys)
    for i, it in enumerate(items):
        base = slugify_key(it.header, i)
        key = base
        n = 2
        while key in seen:
            key = f"{base}_{n}"
            n += 1
        seen.add(key)
        out.append(ReviewQuestion(key=key, header=it.header, question=it.question))
    return out


def _detail(rv: ParallelReview) -> ReviewDetail:
    return ReviewDetail(
        id=rv.id,
        name=rv.name,
        status=rv.status,
        document_ids=rv.document_ids,
        questions=rv.questions,
        results=rv.results,
        created_at=rv.created_at.isoformat(),
        updated_at=rv.updated_at.isoformat(),
    )


async def _tenant_llm(db: AsyncSession, tenant_id: str):
    # Parallel Review is structured extraction -> route it through the "extract"
    # task, so an operator can point extraction at a cheaper/stronger model (e.g.
    # Gemini Flash) without touching this code. A tenant's own provider override
    # still wins over task routing.
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        return get_tenant_task_llm(LLMTask.EXTRACT, None, None)
    return get_tenant_task_llm(LLMTask.EXTRACT, tenant.llm_provider_override, tenant.llm_model_override)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", response_model=ReviewDetail, status_code=201)
async def create_review(
    body: CreateReviewRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    if len(body.document_ids) > MAX_DOCUMENTS:
        raise HTTPException(400, detail=f"At most {MAX_DOCUMENTS} documents per review.")
    if len(body.questions) > MAX_QUESTIONS:
        raise HTTPException(400, detail=f"At most {MAX_QUESTIONS} questions per review.")

    # De-duplicate document ids while preserving order.
    doc_ids = list(dict.fromkeys(body.document_ids))

    docs, missing, not_ready = await load_document_texts(db, current_user.tenant_id, doc_ids)
    if missing:
        raise HTTPException(404, detail=f"Documents not found: {missing}")
    if not_ready:
        raise HTTPException(400, detail=f"Documents still processing (not ready): {not_ready}")

    questions = _build_questions(body.questions, existing_keys=set())

    llm = await _tenant_llm(db, current_user.tenant_id)
    results = await run_review(llm, docs, questions)

    review = ParallelReview(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=body.name,
        document_ids=doc_ids,
        questions=[{"key": q.key, "header": q.header, "question": q.question} for q in questions],
        results=results,
        status="complete",
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    logger.info(
        "parallel_review created",
        extra={"review_id": review.id, "tenant_id": current_user.tenant_id,
               "documents": len(doc_ids), "questions": len(questions)},
    )
    return _detail(review)


@router.get("/", response_model=list[ReviewSummary])
async def list_reviews(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    res = await db.execute(
        select(ParallelReview)
        .where(ParallelReview.tenant_id == current_user.tenant_id)
        .order_by(ParallelReview.created_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
    )
    return [
        ReviewSummary(
            id=rv.id,
            name=rv.name,
            status=rv.status,
            document_count=len(rv.document_ids or []),
            question_count=len(rv.questions or []),
            created_at=rv.created_at.isoformat(),
        )
        for rv in res.scalars().all()
    ]


async def _get_owned(db: AsyncSession, tenant_id: str, review_id: str) -> ParallelReview:
    res = await db.execute(
        select(ParallelReview).where(
            ParallelReview.id == review_id,
            ParallelReview.tenant_id == tenant_id,
        )
    )
    rv = res.scalar_one_or_none()
    if rv is None:
        raise HTTPException(404, detail="Review not found")
    return rv


@router.get("/{review_id}", response_model=ReviewDetail)
async def get_review(
    review_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, review_id))


@router.post("/{review_id}/columns", response_model=ReviewDetail)
async def add_columns(
    review_id: str,
    body: AddColumnsRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    rv = await _get_owned(db, current_user.tenant_id, review_id)

    existing_keys = {q["key"] for q in (rv.questions or [])}
    if len(existing_keys) + len(body.questions) > MAX_QUESTIONS:
        raise HTTPException(400, detail=f"A review may have at most {MAX_QUESTIONS} questions.")

    new_questions = _build_questions(body.questions, existing_keys=existing_keys)

    docs, missing, not_ready = await load_document_texts(
        db, current_user.tenant_id, rv.document_ids
    )
    # A document deleted since the review was created is simply skipped for the
    # new columns; its existing cells remain. Only run new questions.
    llm = await _tenant_llm(db, current_user.tenant_id)
    new_results = await run_review(llm, docs, new_questions)

    # Deep-copy so we mutate an independent structure, not the loaded committed
    # state. Mutating the loaded object in place would leave SQLAlchemy's change
    # detection unable to see a diff on the plain JSON column, and the UPDATE
    # would be silently skipped (the new answers would never persist).
    merged = copy.deepcopy(rv.results or {})
    for doc_id, res in new_results.items():
        if doc_id in merged and isinstance(merged[doc_id].get("answers"), dict):
            merged[doc_id]["answers"].update(res["answers"])
            # A truncation or error on the new pass should surface too.
            merged[doc_id]["truncated"] = merged[doc_id].get("truncated") or res["truncated"]
            merged[doc_id]["error"] = res["error"] or merged[doc_id].get("error")
        else:
            merged[doc_id] = res

    rv.questions = (rv.questions or []) + [
        {"key": q.key, "header": q.header, "question": q.question} for q in new_questions
    ]
    rv.results = merged
    # Plain JSON columns don't track mutations — flag both explicitly so the
    # UPDATE always includes them regardless of object-identity heuristics.
    flag_modified(rv, "questions")
    flag_modified(rv, "results")
    await db.commit()
    await db.refresh(rv)
    return _detail(rv)


@router.get("/{review_id}/export")
async def export_review(
    review_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    rv = await _get_owned(db, current_user.tenant_id, review_id)
    data = review_to_docx(rv.name, rv.questions, rv.document_ids, rv.results)
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(rv.name)}"'},
    )


@router.delete("/{review_id}", status_code=204)
async def delete_review(
    review_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    rv = await _get_owned(db, current_user.tenant_id, review_id)
    await db.delete(rv)
    await db.commit()
