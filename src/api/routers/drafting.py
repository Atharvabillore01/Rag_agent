"""Drafting assistant endpoints (feature-implementation-plan §13).

Instruction + optional source documents → a complete, cited document draft.
Grounded in the supplied documents; routed through the `draft` task.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.db.models import Draft, User
from src.db.session import get_db
from src.drafting.engine import generate_draft
from src.export.docx import DOCX_MEDIA, docx_filename, draft_to_docx
from src.providers.factory import LLMTask, get_tenant_task_llm
from src.review.loader import load_document_texts

router = APIRouter(prefix="/drafting", tags=["drafting"])
logger = logging.getLogger(__name__)

MAX_DOCUMENTS = 20


class CreateDraftRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=8000)
    document_ids: list[str] = Field(default_factory=list)
    name: str | None = Field(default=None, max_length=255)


class DraftSummary(BaseModel):
    id: str
    name: str
    status: str
    document_count: int
    created_at: str


class DraftDetail(BaseModel):
    id: str
    name: str
    instruction: str
    status: str
    document_ids: list[str]
    content: str | None
    citations: list | None
    created_at: str
    updated_at: str


def _detail(d: Draft) -> DraftDetail:
    return DraftDetail(
        id=d.id,
        name=d.name,
        instruction=d.instruction,
        status=d.status,
        document_ids=d.document_ids,
        content=d.content,
        citations=d.citations,
        created_at=d.created_at.isoformat(),
        updated_at=d.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, draft_id: str) -> Draft:
    res = await db.execute(
        select(Draft).where(Draft.id == draft_id, Draft.tenant_id == tenant_id)
    )
    d = res.scalar_one_or_none()
    if d is None:
        raise HTTPException(404, detail="Draft not found")
    return d


@router.post("/", response_model=DraftDetail, status_code=201)
async def create_draft(
    body: CreateDraftRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    doc_ids = list(dict.fromkeys(body.document_ids or []))
    if len(doc_ids) > MAX_DOCUMENTS:
        raise HTTPException(400, detail=f"At most {MAX_DOCUMENTS} source documents per draft.")

    docs: list[tuple[str, str, str]] = []
    if doc_ids:
        loaded, missing, not_ready = await load_document_texts(db, current_user.tenant_id, doc_ids)
        if missing:
            raise HTTPException(404, detail=f"Documents not found: {missing}")
        if not_ready:
            raise HTTPException(400, detail=f"Documents still processing (not ready): {not_ready}")
        docs = loaded

    llm = get_tenant_task_llm(LLMTask.DRAFT, None, None)
    result = await generate_draft(llm, body.instruction, docs)

    default_name = (body.instruction.strip()[:60] + ("…" if len(body.instruction.strip()) > 60 else "")) or "Draft"
    draft = Draft(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=body.name or default_name,
        instruction=body.instruction,
        document_ids=doc_ids,
        content=result["content"],
        citations=result["citations"],
        status="complete",
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)
    logger.info(
        "draft created",
        extra={"draft_id": draft.id, "tenant_id": current_user.tenant_id, "documents": len(doc_ids)},
    )
    return _detail(draft)


@router.get("/", response_model=list[DraftSummary])
async def list_drafts(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    res = await db.execute(
        select(Draft)
        .where(Draft.tenant_id == current_user.tenant_id)
        .order_by(Draft.created_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
    )
    return [
        DraftSummary(
            id=d.id,
            name=d.name,
            status=d.status,
            document_count=len(d.document_ids or []),
            created_at=d.created_at.isoformat(),
        )
        for d in res.scalars().all()
    ]


@router.get("/{draft_id}", response_model=DraftDetail)
async def get_draft(
    draft_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, draft_id))


@router.get("/{draft_id}/export")
async def export_draft(
    draft_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    d = await _get_owned(db, current_user.tenant_id, draft_id)
    data = draft_to_docx(d.name, d.content)
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(d.name)}"'},
    )


@router.delete("/{draft_id}", status_code=204)
async def delete_draft(
    draft_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    d = await _get_owned(db, current_user.tenant_id, draft_id)
    await db.delete(d)
    await db.commit()
