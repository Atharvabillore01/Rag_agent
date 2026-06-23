"""Document upload and management endpoints (§3, §15.1)."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.api.deps import get_object_store_dep, get_vector_store_dep
from src.config import get_settings
from src.db.models import Document, DocumentStatus, Tenant, User
from src.db.session import get_db
from src.ingestion.parsers.router import detect_file_type
from src.storage.object import ObjectStore, sha256_of_bytes
from src.storage.vector import VectorStore

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}


class DocumentResponse(BaseModel):
    document_id: str
    status: str
    filename: str
    message: str


class DocumentListItem(BaseModel):
    document_id: str
    filename: str
    file_type: str
    status: str
    page_count: int | None
    created_at: str


@router.post("/upload", response_model=DocumentResponse, status_code=202)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store_dep),
):
    """Upload a document and enqueue it for async ingestion."""
    import asyncio
    loop = asyncio.get_running_loop()

    # Validate extension
    filename = file.filename or "unknown"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext!r} not supported")

    # Read and validate size
    data = await file.read()
    max_size = (
        settings.demo_max_upload_size_bytes
        if current_user.role.value == "demo"
        else settings.max_upload_size_bytes
    )
    if len(data) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {max_size // (1024*1024)} MB",
        )

    # Quota check — enforce per-tenant document limit
    tenant_row = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant_obj = tenant_row.scalar_one_or_none()
    if tenant_obj:
        count_row = await db.execute(
            select(func.count()).select_from(Document)
            .where(Document.tenant_id == current_user.tenant_id)
        )
        doc_count = count_row.scalar_one()
        if doc_count >= tenant_obj.quota_documents:
            raise HTTPException(
                status_code=429,
                detail=f"Document quota reached ({tenant_obj.quota_documents} documents). "
                       "Delete existing documents to upload more.",
            )

    # Duplicate detection via SHA-256 (§16.3)
    content_hash = sha256_of_bytes(data)
    existing = await db.execute(
        select(Document).where(
            Document.tenant_id == current_user.tenant_id,
            Document.content_hash == content_hash,
        )
    )
    if dup := existing.scalar_one_or_none():
        return DocumentResponse(
            document_id=dup.id,
            status=dup.status.value,
            filename=filename,
            message="Duplicate document — this file was already uploaded.",
        )

    # Detect file type
    mime = file.content_type
    file_type = detect_file_type(filename, mime)

    # Upload to object storage — boto3 is synchronous; run in thread pool so
    # the async event loop is not blocked during the network transfer.
    document_id = str(uuid.uuid4())
    storage_key = ObjectStore.document_key(current_user.tenant_id, document_id, filename)
    await loop.run_in_executor(
        None,
        lambda: object_store.upload(storage_key, data, content_type=mime or "application/octet-stream"),
    )

    # Create document record
    doc = Document(
        id=document_id,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.id,
        filename=filename,
        file_type=file_type,
        storage_path=storage_key,
        content_hash=content_hash,
        status=DocumentStatus.uploaded,
        file_size_bytes=len(data),
    )
    db.add(doc)
    await db.commit()

    # Enqueue ingestion job
    from src.ingestion.worker import run_ingestion_pipeline
    queue = (
        settings.ingestion_demo_queue
        if current_user.role.value == "demo"
        else settings.ingestion_fast_queue
    )
    run_ingestion_pipeline.apply_async(
        kwargs={
            "document_id": document_id,
            "tenant_id": current_user.tenant_id,
            "storage_path": storage_key,
            "file_type": file_type,
            "ingestion_version": 1,
            "collection_tags": current_user.collection_tags,
        },
        queue=queue,
    )

    return DocumentResponse(
        document_id=document_id,
        status=DocumentStatus.uploaded.value,
        filename=filename,
        message="Document uploaded and queued for processing.",
    )


@router.get("/", response_model=list[DocumentListItem])
async def list_documents(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == current_user.tenant_id)
        .offset(skip)
        .limit(limit)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        DocumentListItem(
            document_id=d.id,
            filename=d.filename,
            file_type=d.file_type,
            status=d.status.value,
            page_count=d.page_count,
            created_at=d.created_at.isoformat(),
        )
        for d in docs
    ]


@router.get("/{document_id}", response_model=DocumentListItem)
async def get_document(
    document_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentListItem(
        document_id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        status=doc.status.value,
        page_count=doc.page_count,
        created_at=doc.created_at.isoformat(),
    )


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store_dep),
    vector_store: VectorStore = Depends(get_vector_store_dep),
):
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    import asyncio
    loop = asyncio.get_running_loop()

    # Run synchronous boto3 deletes in thread pool to avoid blocking the event loop
    await loop.run_in_executor(None, lambda: object_store.delete_prefix(f"raw/{current_user.tenant_id}/{document_id}/"))
    await loop.run_in_executor(None, lambda: object_store.delete_prefix(f"artifacts/{current_user.tenant_id}/{document_id}/"))
    await vector_store.delete_by_document(current_user.tenant_id, document_id)
    await db.delete(doc)
    await db.commit()
