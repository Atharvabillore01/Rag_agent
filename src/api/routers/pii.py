"""Sensitive-data scan & redaction endpoints (feature-implementation-plan §28).

Scan selected documents for PII / sensitive identifiers and produce a masked
findings report plus a redacted export. Privacy by design: only masked findings
are stored; the redacted export re-derives from the live document at export time,
so raw values are never persisted.
"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.db.models import SensitiveScan, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, docx_filename, redaction_to_docx
from src.pii.engine import MAX_DOCS, redact_text, run_scan
from src.api.deps import resolve_task_llm
from src.providers.factory import LLMTask
from src.review.loader import load_document_chunks, load_document_texts

router = APIRouter(prefix="/pii", tags=["pii"])
logger = logging.getLogger(__name__)


class CreateScanRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    document_ids: list[str] = Field(min_length=1, max_length=MAX_DOCS)
    use_llm: bool = False  # also detect person names / addresses via the LLM


class ScanSummary(BaseModel):
    id: str
    name: str
    status: str
    document_count: int
    finding_count: int
    created_at: str


class ScanDetail(BaseModel):
    id: str
    name: str
    status: str
    document_ids: list
    results: list | None
    summary: dict | None
    created_at: str
    updated_at: str


def _detail(sc: SensitiveScan) -> ScanDetail:
    return ScanDetail(
        id=sc.id,
        name=sc.name,
        status=sc.status,
        document_ids=sc.document_ids or [],
        results=sc.results,
        summary=sc.summary,
        created_at=sc.created_at.isoformat(),
        updated_at=sc.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, scan_id: str) -> SensitiveScan:
    res = await db.execute(
        select(SensitiveScan).where(
            SensitiveScan.id == scan_id, SensitiveScan.tenant_id == tenant_id
        )
    )
    sc = res.scalar_one_or_none()
    if sc is None:
        raise HTTPException(404, detail="Scan not found")
    return sc


@router.post("/", response_model=ScanDetail, status_code=201)
async def create_scan(
    body: CreateScanRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    seen: set[str] = set()
    doc_ids = [i for i in body.document_ids if not (i in seen or seen.add(i))]

    chunks, missing, not_ready = await load_document_chunks(db, current_user.tenant_id, doc_ids)
    if missing:
        raise HTTPException(404, detail=f"Documents not found: {missing}")
    if not_ready:
        raise HTTPException(400, detail=f"Documents still processing (not ready): {not_ready}")
    if not chunks:
        raise HTTPException(400, detail="No readable document text to scan.")

    llm = await resolve_task_llm(db, current_user.tenant_id, LLMTask.EXTRACT) if body.use_llm else None
    scanned = await run_scan(chunks, llm=llm)

    default_name = "Sensitive scan: " + ", ".join(
        sorted({c["filename"] for c in chunks if c.get("filename")})
    )[:200]
    scan = SensitiveScan(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        name=(body.name or default_name)[:255],
        document_ids=doc_ids,
        results=scanned["results"],
        summary=scanned["summary"],
        status="complete",
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)
    logger.info(
        "sensitive scan created",
        extra={
            "scan_id": scan.id, "tenant_id": current_user.tenant_id,
            "documents": len(doc_ids), "findings": scanned["summary"].get("total", 0),
        },
    )
    return _detail(scan)


@router.get("/", response_model=list[ScanSummary])
async def list_scans(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    offset = max(0, skip)
    page = min(max(1, limit), 100)
    res = await db.execute(
        select(SensitiveScan)
        .where(SensitiveScan.tenant_id == current_user.tenant_id)
        .order_by(SensitiveScan.created_at.desc())
        .offset(offset)
        .limit(page)
    )
    return [
        ScanSummary(
            id=sc.id,
            name=sc.name,
            status=sc.status,
            document_count=len(sc.document_ids or []),
            finding_count=(sc.summary or {}).get("total", 0),
            created_at=sc.created_at.isoformat(),
        )
        for sc in res.scalars().all()
    ]


@router.get("/{scan_id}", response_model=ScanDetail)
async def get_scan(
    scan_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, scan_id))


@router.get("/{scan_id}/export")
async def export_redacted(
    scan_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Redacted DOCX. Re-derives from the live documents (tenant-scoped) so raw
    values are never read from storage we persisted."""
    sc = await _get_owned(db, current_user.tenant_id, scan_id)
    docs, missing, not_ready = await load_document_texts(
        db, current_user.tenant_id, sc.document_ids or []
    )
    sections = []
    for _doc_id, filename, text in docs:
        # redaction is CPU-bound (regex over full document text) — offload it so a
        # large document cannot block the event loop on this unmetered GET.
        redacted, count = await asyncio.to_thread(redact_text, text)
        sections.append({"filename": filename, "redacted_text": redacted, "count": count})
    data = redaction_to_docx(sc.name, sections, unavailable=len(missing) + len(not_ready))
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(sc.name)}"'},
    )


@router.delete("/{scan_id}", status_code=204)
async def delete_scan(
    scan_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    sc = await _get_owned(db, current_user.tenant_id, scan_id)
    await db.delete(sc)
    await db.commit()
