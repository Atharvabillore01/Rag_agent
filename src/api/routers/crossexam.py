"""Cross-Examination generator endpoints (feature-implementation-plan §29).

Generate a themed cross-examination plan from selected documents. Uses ONLY the
tenant's own, ready documents (src/review/loader) — no external retrieval, no
cross-tenant data.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.crossexam.engine import MAX_DOCS, generate_cross_exam
from src.db.models import CrossExam, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, cross_exam_to_docx, docx_filename
from src.api.deps import resolve_task_llm
from src.providers.factory import LLMTask
from src.review.loader import load_document_texts

router = APIRouter(prefix="/cross-exam", tags=["cross-exam"])
logger = logging.getLogger(__name__)


class CreateCrossExamRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    document_ids: list[str] = Field(min_length=1, max_length=MAX_DOCS)
    instruction: str | None = Field(default=None, max_length=4000)


class CrossExamSummary(BaseModel):
    id: str
    name: str
    status: str
    document_count: int
    question_count: int
    created_at: str


class CrossExamDetail(BaseModel):
    id: str
    name: str
    status: str
    document_ids: list
    instruction: str | None
    results: list | None
    created_at: str
    updated_at: str


def _question_count(results) -> int:
    return sum(len(t.get("questions") or []) for t in (results or []))


def _detail(ce: CrossExam) -> CrossExamDetail:
    return CrossExamDetail(
        id=ce.id,
        name=ce.name,
        status=ce.status,
        document_ids=ce.document_ids or [],
        instruction=ce.instruction,
        results=ce.results,
        created_at=ce.created_at.isoformat(),
        updated_at=ce.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, ce_id: str) -> CrossExam:
    res = await db.execute(
        select(CrossExam).where(CrossExam.id == ce_id, CrossExam.tenant_id == tenant_id)
    )
    ce = res.scalar_one_or_none()
    if ce is None:
        raise HTTPException(404, detail="Cross-examination plan not found")
    return ce


@router.post("/", response_model=CrossExamDetail, status_code=201)
async def create_cross_exam(
    body: CreateCrossExamRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    seen: set[str] = set()
    doc_ids = [i for i in body.document_ids if not (i in seen or seen.add(i))]

    docs, missing, not_ready = await load_document_texts(db, current_user.tenant_id, doc_ids)
    if missing:
        raise HTTPException(404, detail=f"Documents not found: {missing}")
    if not_ready:
        raise HTTPException(400, detail=f"Documents still processing (not ready): {not_ready}")
    if not docs:
        raise HTTPException(400, detail="At least one ready document is required.")

    llm = await resolve_task_llm(db, current_user.tenant_id, LLMTask.DRAFT)
    topics = await generate_cross_exam(llm, docs, body.instruction)

    default_name = "Cross-examination: " + ", ".join(f for _, f, _ in docs[:3])
    ce = CrossExam(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=(body.name or default_name)[:255],
        document_ids=[d[0] for d in docs],
        instruction=body.instruction,
        results=topics,
        status="complete",
    )
    db.add(ce)
    await db.commit()
    await db.refresh(ce)
    logger.info(
        "cross-exam created",
        extra={"cross_exam_id": ce.id, "tenant_id": current_user.tenant_id,
               "documents": len(docs), "questions": _question_count(topics)},
    )
    return _detail(ce)


@router.get("/", response_model=list[CrossExamSummary])
async def list_cross_exams(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    offset = max(0, skip)
    page = min(max(1, limit), 100)
    res = await db.execute(
        select(CrossExam)
        .where(CrossExam.tenant_id == current_user.tenant_id)
        .order_by(CrossExam.created_at.desc())
        .offset(offset)
        .limit(page)
    )
    return [
        CrossExamSummary(
            id=ce.id,
            name=ce.name,
            status=ce.status,
            document_count=len(ce.document_ids or []),
            question_count=_question_count(ce.results),
            created_at=ce.created_at.isoformat(),
        )
        for ce in res.scalars().all()
    ]


@router.get("/{ce_id}", response_model=CrossExamDetail)
async def get_cross_exam(
    ce_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, ce_id))


@router.get("/{ce_id}/export")
async def export_cross_exam(
    ce_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    ce = await _get_owned(db, current_user.tenant_id, ce_id)
    data = cross_exam_to_docx(ce.name, ce.results)
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(ce.name)}"'},
    )


@router.delete("/{ce_id}", status_code=204)
async def delete_cross_exam(
    ce_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    ce = await _get_owned(db, current_user.tenant_id, ce_id)
    await db.delete(ce)
    await db.commit()
