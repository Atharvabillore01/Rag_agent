"""Redline / document-diff endpoints (feature-implementation-plan §8).

Compare two documents and return a Change -> Consequence table. The diff is
computed deterministically; the LLM only explains each change's consequence.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.db.models import Redline, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, docx_filename, redline_to_docx
from src.providers.factory import LLMTask, get_tenant_task_llm
from src.redline.engine import run_redline
from src.review.loader import load_document_texts

router = APIRouter(prefix="/redline", tags=["redline"])
logger = logging.getLogger(__name__)


class CreateRedlineRequest(BaseModel):
    base_document_id: str = Field(min_length=1)
    revised_document_id: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=255)


class RedlineSummary(BaseModel):
    id: str
    name: str
    status: str
    change_count: int
    created_at: str


class RedlineDetail(BaseModel):
    id: str
    name: str
    status: str
    base_document_id: str
    revised_document_id: str
    results: list | None
    created_at: str
    updated_at: str


def _detail(rl: Redline) -> RedlineDetail:
    return RedlineDetail(
        id=rl.id,
        name=rl.name,
        status=rl.status,
        base_document_id=rl.base_document_id,
        revised_document_id=rl.revised_document_id,
        results=rl.results,
        created_at=rl.created_at.isoformat(),
        updated_at=rl.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, redline_id: str) -> Redline:
    res = await db.execute(
        select(Redline).where(Redline.id == redline_id, Redline.tenant_id == tenant_id)
    )
    rl = res.scalar_one_or_none()
    if rl is None:
        raise HTTPException(404, detail="Redline not found")
    return rl


@router.post("/", response_model=RedlineDetail, status_code=201)
async def create_redline(
    body: CreateRedlineRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    if body.base_document_id == body.revised_document_id:
        raise HTTPException(400, detail="Select two different documents to compare.")

    ordered = [body.base_document_id, body.revised_document_id]
    docs, missing, not_ready = await load_document_texts(db, current_user.tenant_id, ordered)
    if missing:
        raise HTTPException(404, detail=f"Documents not found: {missing}")
    if not_ready:
        raise HTTPException(400, detail=f"Documents still processing (not ready): {not_ready}")

    by_id = {doc_id: (fname, text) for doc_id, fname, text in docs}
    base_name, base_text = by_id[body.base_document_id]
    revised_name, revised_text = by_id[body.revised_document_id]

    llm = get_tenant_task_llm(LLMTask.EXTRACT, None, None)
    results = await run_redline(llm, base_text, revised_text)

    redline = Redline(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=body.name or f"{base_name} vs {revised_name}",
        base_document_id=body.base_document_id,
        revised_document_id=body.revised_document_id,
        results=results,
        status="complete",
    )
    db.add(redline)
    await db.commit()
    await db.refresh(redline)
    logger.info(
        "redline created",
        extra={"redline_id": redline.id, "tenant_id": current_user.tenant_id, "changes": len(results)},
    )
    return _detail(redline)


@router.get("/", response_model=list[RedlineSummary])
async def list_redlines(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    res = await db.execute(
        select(Redline)
        .where(Redline.tenant_id == current_user.tenant_id)
        .order_by(Redline.created_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
    )
    return [
        RedlineSummary(
            id=rl.id,
            name=rl.name,
            status=rl.status,
            change_count=len(rl.results or []),
            created_at=rl.created_at.isoformat(),
        )
        for rl in res.scalars().all()
    ]


@router.get("/{redline_id}", response_model=RedlineDetail)
async def get_redline(
    redline_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, redline_id))


@router.get("/{redline_id}/export")
async def export_redline(
    redline_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    rl = await _get_owned(db, current_user.tenant_id, redline_id)
    data = redline_to_docx(rl.name, rl.results)
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(rl.name)}"'},
    )


@router.delete("/{redline_id}", status_code=204)
async def delete_redline(
    redline_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    rl = await _get_owned(db, current_user.tenant_id, redline_id)
    await db.delete(rl)
    await db.commit()
