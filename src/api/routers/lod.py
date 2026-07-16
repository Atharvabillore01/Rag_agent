"""List of Dates (chronology) endpoints (feature-implementation-plan §11).

Build a chronological List of Dates from one or more documents. Dates are found
deterministically in the source (no hallucinated dates); the LLM summarizes each
event and normalizes it for sorting. Routed through the `extract` task.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.db.models import ListOfDates, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, docx_filename, lod_to_docx
from src.lod.engine import run_lod
from src.providers.factory import LLMTask, get_tenant_task_llm
from src.review.loader import load_document_chunks

router = APIRouter(prefix="/lod", tags=["lod"])
logger = logging.getLogger(__name__)

MAX_DOCUMENTS = 25


class CreateLodRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1)
    name: str | None = Field(default=None, max_length=255)


class LodSummary(BaseModel):
    id: str
    name: str
    status: str
    document_count: int
    entry_count: int
    created_at: str


class LodDetail(BaseModel):
    id: str
    name: str
    status: str
    document_ids: list[str]
    results: list | None
    created_at: str
    updated_at: str


def _detail(l: ListOfDates) -> LodDetail:
    return LodDetail(
        id=l.id,
        name=l.name,
        status=l.status,
        document_ids=l.document_ids,
        results=l.results,
        created_at=l.created_at.isoformat(),
        updated_at=l.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, lod_id: str) -> ListOfDates:
    res = await db.execute(
        select(ListOfDates).where(ListOfDates.id == lod_id, ListOfDates.tenant_id == tenant_id)
    )
    l = res.scalar_one_or_none()
    if l is None:
        raise HTTPException(404, detail="List of Dates not found")
    return l


@router.post("/", response_model=LodDetail, status_code=201)
async def create_lod(
    body: CreateLodRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    doc_ids = list(dict.fromkeys(body.document_ids))
    if len(doc_ids) > MAX_DOCUMENTS:
        raise HTTPException(400, detail=f"At most {MAX_DOCUMENTS} documents per List of Dates.")

    chunks, missing, not_ready = await load_document_chunks(db, current_user.tenant_id, doc_ids)
    if missing:
        raise HTTPException(404, detail=f"Documents not found: {missing}")
    if not_ready:
        raise HTTPException(400, detail=f"Documents still processing (not ready): {not_ready}")

    llm = get_tenant_task_llm(LLMTask.EXTRACT, None, None)
    results = await run_lod(llm, chunks)

    # Default name from the first document (+N more).
    first_name = chunks[0]["filename"] if chunks else "documents"
    default_name = f"List of Dates — {first_name}" + (
        f" +{len(doc_ids) - 1} more" if len(doc_ids) > 1 else ""
    )

    lod = ListOfDates(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=body.name or default_name,
        document_ids=doc_ids,
        results=results,
        status="complete",
    )
    db.add(lod)
    await db.commit()
    await db.refresh(lod)
    logger.info(
        "list_of_dates created",
        extra={"lod_id": lod.id, "tenant_id": current_user.tenant_id,
               "documents": len(doc_ids), "entries": len(results)},
    )
    return _detail(lod)


@router.get("/", response_model=list[LodSummary])
async def list_lods(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    res = await db.execute(
        select(ListOfDates)
        .where(ListOfDates.tenant_id == current_user.tenant_id)
        .order_by(ListOfDates.created_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
    )
    return [
        LodSummary(
            id=l.id,
            name=l.name,
            status=l.status,
            document_count=len(l.document_ids or []),
            entry_count=len(l.results or []),
            created_at=l.created_at.isoformat(),
        )
        for l in res.scalars().all()
    ]


@router.get("/{lod_id}", response_model=LodDetail)
async def get_lod(
    lod_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, lod_id))


@router.get("/{lod_id}/export")
async def export_lod(
    lod_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    l = await _get_owned(db, current_user.tenant_id, lod_id)
    data = lod_to_docx(l.name, l.results)
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(l.name)}"'},
    )


@router.delete("/{lod_id}", status_code=204)
async def delete_lod(
    lod_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    l = await _get_owned(db, current_user.tenant_id, lod_id)
    await db.delete(l)
    await db.commit()
