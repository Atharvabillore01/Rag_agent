"""Folder / matter endpoints (feature-implementation-plan §23)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.db.models import Document, Folder, User
from src.db.session import get_db

router = APIRouter(prefix="/folders", tags=["folders"])
logger = logging.getLogger(__name__)


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class RenameFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FolderResponse(BaseModel):
    id: str
    name: str
    document_count: int
    created_at: str


async def _get_owned(db: AsyncSession, tenant_id: str, folder_id: str) -> Folder:
    res = await db.execute(
        select(Folder).where(Folder.id == folder_id, Folder.tenant_id == tenant_id)
    )
    f = res.scalar_one_or_none()
    if f is None:
        raise HTTPException(404, detail="Folder not found")
    return f


@router.post("/", response_model=FolderResponse, status_code=201)
async def create_folder(
    body: CreateFolderRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    folder = Folder(tenant_id=current_user.tenant_id, created_by=current_user.id, name=body.name.strip())
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return FolderResponse(id=folder.id, name=folder.name, document_count=0, created_at=folder.created_at.isoformat())


@router.get("/", response_model=list[FolderResponse])
async def list_folders(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(Folder).where(Folder.tenant_id == current_user.tenant_id).order_by(Folder.name)
    )
    folders = res.scalars().all()
    # Per-folder document counts in one query.
    counts: dict[str, int] = {}
    if folders:
        crows = await db.execute(
            select(Document.folder_id, func.count())
            .where(Document.tenant_id == current_user.tenant_id, Document.folder_id.isnot(None))
            .group_by(Document.folder_id)
        )
        counts = {fid: n for fid, n in crows.all()}
    return [
        FolderResponse(id=f.id, name=f.name, document_count=counts.get(f.id, 0), created_at=f.created_at.isoformat())
        for f in folders
    ]


@router.patch("/{folder_id}", response_model=FolderResponse)
async def rename_folder(
    folder_id: str,
    body: RenameFolderRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    folder = await _get_owned(db, current_user.tenant_id, folder_id)
    folder.name = body.name.strip()
    await db.commit()
    await db.refresh(folder)
    count = (await db.execute(
        select(func.count()).select_from(Document).where(Document.folder_id == folder_id)
    )).scalar_one()
    return FolderResponse(id=folder.id, name=folder.name, document_count=count, created_at=folder.created_at.isoformat())


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """Delete a folder. Its documents are unfiled (folder_id -> NULL), not deleted."""
    folder = await _get_owned(db, current_user.tenant_id, folder_id)
    await db.delete(folder)
    await db.commit()
