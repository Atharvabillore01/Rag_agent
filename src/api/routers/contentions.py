"""Contentions Comparison endpoints (feature-implementation-plan §26).

Compare the rival contentions across a set of pleadings: the disputed issues are
derived by the model, each pleading's stance on each issue is classified, and an
overall dispute summary is written. Analysis uses ONLY the selected, tenant-owned
documents (see src/review/loader + src/contentions/engine) — no external
retrieval and no cross-tenant data.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.contentions.engine import MAX_DOCS, run_contentions
from src.db.models import ContentionAnalysis, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, contentions_to_docx, docx_filename
from src.providers.factory import LLMTask, get_tenant_task_llm
from src.review.loader import load_document_texts

router = APIRouter(prefix="/contentions", tags=["contentions"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateContentionsRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    # Cap at MAX_DOCS at parse time so an oversized array is rejected by validation
    # (422) before the router materializes/de-dupes it in memory.
    document_ids: list[str] = Field(min_length=2, max_length=MAX_DOCS)


class ContentionsSummary(BaseModel):
    id: str
    name: str
    status: str
    document_count: int
    issue_count: int
    created_at: str


class ContentionsDetail(BaseModel):
    id: str
    name: str
    status: str
    document_ids: list
    issues: list | None
    results: list | None
    summary: str | None
    created_at: str
    updated_at: str


def _detail(ca: ContentionAnalysis) -> ContentionsDetail:
    return ContentionsDetail(
        id=ca.id,
        name=ca.name,
        status=ca.status,
        document_ids=ca.document_ids or [],
        issues=ca.issues,
        results=ca.results,
        summary=ca.summary,
        created_at=ca.created_at.isoformat(),
        updated_at=ca.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, analysis_id: str) -> ContentionAnalysis:
    res = await db.execute(
        select(ContentionAnalysis).where(
            ContentionAnalysis.id == analysis_id,
            ContentionAnalysis.tenant_id == tenant_id,
        )
    )
    ca = res.scalar_one_or_none()
    if ca is None:
        raise HTTPException(404, detail="Contentions analysis not found")
    return ca


@router.post("/", response_model=ContentionsDetail, status_code=201)
async def create_contentions(
    body: CreateContentionsRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    # Preserve selection order, drop duplicates.
    seen: set[str] = set()
    doc_ids = [i for i in body.document_ids if not (i in seen or seen.add(i))]
    if len(doc_ids) < 2:
        raise HTTPException(400, detail="Select at least two different pleadings to compare.")
    if len(doc_ids) > MAX_DOCS:
        raise HTTPException(400, detail=f"Select at most {MAX_DOCS} pleadings.")

    docs, missing, not_ready = await load_document_texts(db, current_user.tenant_id, doc_ids)
    if missing:
        raise HTTPException(404, detail=f"Documents not found: {missing}")
    if not_ready:
        raise HTTPException(400, detail=f"Documents still processing (not ready): {not_ready}")
    if len(docs) < 2:
        raise HTTPException(400, detail="At least two ready documents are required.")

    llm = get_tenant_task_llm(LLMTask.EXTRACT, None, None)
    result = await run_contentions(llm, docs)

    default_name = "Contentions: " + " vs ".join(f for _, f, _ in docs[:3])
    analysis = ContentionAnalysis(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=(body.name or default_name)[:255],
        document_ids=[d[0] for d in docs],
        issues=result["issues"],
        results=result["results"],
        summary=result["summary"],
        status="complete",
    )
    db.add(analysis)
    await db.commit()
    await db.refresh(analysis)
    logger.info(
        "contentions analysis created",
        extra={
            "analysis_id": analysis.id,
            "tenant_id": current_user.tenant_id,
            "documents": len(docs),
            "issues": len(result["issues"]),
        },
    )
    return _detail(analysis)


@router.get("/", response_model=list[ContentionsSummary])
async def list_contentions(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    # Clamp pagination so a negative skip/limit can't reach Postgres (which 500s on
    # a negative OFFSET/LIMIT) and limit stays bounded.
    offset = max(0, skip)
    page = min(max(1, limit), 100)
    res = await db.execute(
        select(ContentionAnalysis)
        .where(ContentionAnalysis.tenant_id == current_user.tenant_id)
        .order_by(ContentionAnalysis.created_at.desc())
        .offset(offset)
        .limit(page)
    )
    return [
        ContentionsSummary(
            id=ca.id,
            name=ca.name,
            status=ca.status,
            document_count=len(ca.document_ids or []),
            issue_count=len(ca.issues or []),
            created_at=ca.created_at.isoformat(),
        )
        for ca in res.scalars().all()
    ]


@router.get("/{analysis_id}", response_model=ContentionsDetail)
async def get_contentions(
    analysis_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, analysis_id))


@router.get("/{analysis_id}/export")
async def export_contentions(
    analysis_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    ca = await _get_owned(db, current_user.tenant_id, analysis_id)
    data = contentions_to_docx(ca.name, ca.issues, ca.results, ca.summary)
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(ca.name)}"'},
    )


@router.delete("/{analysis_id}", status_code=204)
async def delete_contentions(
    analysis_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    ca = await _get_owned(db, current_user.tenant_id, analysis_id)
    await db.delete(ca)
    await db.commit()
