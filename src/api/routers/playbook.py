"""Contract Playbook Review endpoints (feature-implementation-plan §30).

Assess a contract against a playbook of standard positions. Uses ONLY the tenant's
own, ready documents (src/review/loader) — no external retrieval, no cross-tenant
data.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from src.api.auth import require_editor, require_viewer
from src.api.deps import resolve_task_llm
from src.db.models import PlaybookReview, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, docx_filename, playbook_to_docx
from src.playbook.engine import DEFAULT_PLAYBOOK, MAX_DOCS, merge_playbook, run_playbook_review
from src.providers.factory import LLMTask
from src.review.loader import load_document_texts

# Document ids are UUIDs — bound each string so an oversized JSON body can't
# amplify memory before validation.
DocId = Annotated[str, StringConstraints(min_length=1, max_length=64)]

router = APIRouter(prefix="/playbook", tags=["playbook"])
logger = logging.getLogger(__name__)


class PlaybookClause(BaseModel):
    clause_type: str = Field(min_length=1, max_length=120)
    standard: str = Field(min_length=1, max_length=1000)


class CreatePlaybookRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    document_ids: list[DocId] = Field(min_length=1, max_length=MAX_DOCS)
    # optional custom clauses that merge over / extend the built-in default playbook
    playbook: list[PlaybookClause] | None = Field(default=None, max_length=40)


class PlaybookSummary(BaseModel):
    id: str
    name: str
    status: str
    document_count: int
    high_risk_count: int
    created_at: str


class PlaybookDetail(BaseModel):
    id: str
    name: str
    status: str
    document_ids: list
    playbook: list | None
    results: list | None
    summary: dict | None
    created_at: str
    updated_at: str


def _detail(pr: PlaybookReview) -> PlaybookDetail:
    return PlaybookDetail(
        id=pr.id,
        name=pr.name,
        status=pr.status,
        document_ids=pr.document_ids or [],
        playbook=pr.playbook,
        results=pr.results,
        summary=pr.summary,
        created_at=pr.created_at.isoformat(),
        updated_at=pr.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, pr_id: str) -> PlaybookReview:
    res = await db.execute(
        select(PlaybookReview).where(PlaybookReview.id == pr_id, PlaybookReview.tenant_id == tenant_id)
    )
    pr = res.scalar_one_or_none()
    if pr is None:
        raise HTTPException(404, detail="Playbook review not found")
    return pr


@router.get("/default")
async def get_default_playbook(current_user: User = Depends(require_viewer)):
    """The built-in default playbook, so the UI can show/edit it before running."""
    return {"playbook": DEFAULT_PLAYBOOK}


@router.post("/", response_model=PlaybookDetail, status_code=201)
async def create_playbook_review(
    body: CreatePlaybookRequest,
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

    custom = [c.model_dump() for c in body.playbook] if body.playbook else None
    effective = merge_playbook(custom)

    llm = await resolve_task_llm(db, current_user.tenant_id, LLMTask.EXTRACT)
    result = await run_playbook_review(llm, docs, effective)

    default_name = "Playbook review: " + ", ".join(f for _, f, _ in docs[:3])
    pr = PlaybookReview(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=(body.name or default_name)[:255],
        document_ids=[d[0] for d in docs],
        playbook=result["playbook"],
        results=result["results"],
        summary=result["summary"],
        status="complete",
    )
    db.add(pr)
    await db.commit()
    await db.refresh(pr)
    logger.info(
        "playbook review created",
        extra={"playbook_review_id": pr.id, "tenant_id": current_user.tenant_id,
               "documents": len(docs), "clauses": len(result["results"])},
    )
    return _detail(pr)


@router.get("/", response_model=list[PlaybookSummary])
async def list_playbook_reviews(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    offset = max(0, skip)
    page = min(max(1, limit), 100)
    # Only load the columns the summary needs — avoid fetching the large results/
    # playbook JSON blobs that the list response never returns.
    res = await db.execute(
        select(PlaybookReview)
        .options(load_only(
            PlaybookReview.id, PlaybookReview.name, PlaybookReview.status,
            PlaybookReview.document_ids, PlaybookReview.summary, PlaybookReview.created_at,
        ))
        .where(PlaybookReview.tenant_id == current_user.tenant_id)
        .order_by(PlaybookReview.created_at.desc())
        .offset(offset)
        .limit(page)
    )
    return [
        PlaybookSummary(
            id=pr.id,
            name=pr.name,
            status=pr.status,
            document_count=len(pr.document_ids or []),
            high_risk_count=(pr.summary or {}).get("by_risk", {}).get("high", 0),
            created_at=pr.created_at.isoformat(),
        )
        for pr in res.scalars().all()
    ]


@router.get("/{pr_id}", response_model=PlaybookDetail)
async def get_playbook_review(
    pr_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, pr_id))


@router.get("/{pr_id}/export")
async def export_playbook_review(
    pr_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    pr = await _get_owned(db, current_user.tenant_id, pr_id)
    data = playbook_to_docx(pr.name, pr.results)
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(pr.name)}"'},
    )


@router.delete("/{pr_id}", status_code=204)
async def delete_playbook_review(
    pr_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    pr = await _get_owned(db, current_user.tenant_id, pr_id)
    await db.delete(pr)
    await db.commit()
