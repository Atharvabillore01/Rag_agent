"""Document upload and management endpoints (§3, §15.1)."""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.api.deps import get_object_store_dep, get_vector_store_dep
from src.config import get_settings
from src.db.models import AuditLog, Document, DocumentStatus, Folder, Tenant, User
from src.db.session import AsyncSessionLocal, get_db
from src.ingestion.content_scan import content_matches
from src.ingestion.parsers.router import detect_file_type
from src.storage.object import ObjectStore, sha256_of_bytes
from src.storage.vector import VectorStore

router = APIRouter(prefix="/documents", tags=["documents"])
settings = get_settings()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp"}


def _req_meta(request: Request) -> dict:
    """G13: capture caller IP + user-agent for the audit trail."""
    fwd = request.headers.get("x-forwarded-for")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")
    return {"ip": ip, "user_agent": request.headers.get("user-agent", "")[:200]}


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
    folder_id: str | None = None


class MoveFolderRequest(BaseModel):
    folder_id: str | None = None


@router.post("/upload", response_model=DocumentResponse, status_code=202)
async def upload_document(
    request: Request,
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

    # Quota check — enforce per-tenant document limit. G8: demo tenants get the
    # stricter demo cap regardless of the tenant's general quota.
    tenant_row = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant_obj = tenant_row.scalar_one_or_none()
    if tenant_obj:
        count_row = await db.execute(
            select(func.count()).select_from(Document)
            .where(Document.tenant_id == current_user.tenant_id)
        )
        doc_count = count_row.scalar_one()
        doc_limit = (
            settings.demo_max_documents
            if current_user.role.value == "demo"
            else tenant_obj.quota_documents
        )
        if doc_count >= doc_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Document quota reached ({doc_limit} documents). "
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

    # G9: reject files whose actual bytes don't match their declared type — a
    # renamed executable/script must not reach the parser posing as a document.
    ok, sniffed = content_matches(data, file_type)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"File content ({sniffed or 'unrecognized'}) does not match a "
                   f"{file_type.upper()} document. Upload rejected.",
        )

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
    db.add(AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="document_upload",
        resource_type="document",
        resource_id=document_id,
        log_metadata={"filename": filename, "file_type": file_type, **_req_meta(request)},
    ))
    await db.commit()
    logger.info(
        "upload queued document",
        extra={
            "document_id": document_id,
            "tenant_id": current_user.tenant_id,
            "uploaded_by": current_user.id,
            "doc_filename": filename,
            "file_size_bytes": len(data),
            "file_type": file_type,
        },
    )

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


# ── Direct-to-storage upload (client → MinIO; presigned + multipart) ──────────
# Production path: the API never buffers the file. init issues a presigned URL (or
# multipart credentials); the client uploads straight to MinIO; complete verifies
# the object, content-scans it, records size/hash, and enqueues async processing.

class UploadInitRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=512)
    content_type: str | None = None
    multipart: bool = False


class UploadInitResponse(BaseModel):
    document_id: str
    storage_key: str
    method: str                      # "single" | "multipart"
    upload_url: str | None = None    # single-part presigned PUT
    upload_id: str | None = None     # multipart upload id


class SignPartRequest(BaseModel):
    upload_id: str
    part_number: int = Field(ge=1, le=10000)


class SignPartResponse(BaseModel):
    url: str


class CompleteUploadRequest(BaseModel):
    upload_id: str | None = None
    parts: list[dict] | None = None  # [{"PartNumber": int, "ETag": str}] for multipart


class AbortUploadRequest(BaseModel):
    upload_id: str


async def _ensure_quota(db: AsyncSession, tenant_id: str) -> None:
    row = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = row.scalar_one_or_none()
    if tenant:
        count = (await db.execute(
            select(func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
        )).scalar_one()
        if count >= tenant.quota_documents:
            raise HTTPException(
                status_code=429,
                detail=f"Document quota reached ({tenant.quota_documents} documents).",
            )


def _enqueue_ingestion(document_id: str, tenant_id: str, storage_key: str, file_type: str,
                       collection_tags, role: str) -> None:
    from src.ingestion.worker import run_ingestion_pipeline
    queue = settings.ingestion_demo_queue if role == "demo" else settings.ingestion_fast_queue
    run_ingestion_pipeline.apply_async(
        kwargs={
            "document_id": document_id, "tenant_id": tenant_id, "storage_path": storage_key,
            "file_type": file_type, "ingestion_version": 1, "collection_tags": collection_tags,
        },
        queue=queue,
    )


async def _owned_pending_doc(db: AsyncSession, tenant_id: str, document_id: str) -> Document:
    doc = (await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.post("/upload-init", response_model=UploadInitResponse, status_code=201)
async def upload_init(
    body: UploadInitRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store_dep),
):
    ext = "." + body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type {ext!r} not supported")
    await _ensure_quota(db, current_user.tenant_id)

    document_id = str(uuid.uuid4())
    file_type = detect_file_type(body.filename, body.content_type)
    storage_key = ObjectStore.document_key(current_user.tenant_id, document_id, body.filename)
    ctype = body.content_type or "application/octet-stream"

    # Row is created up front (status=uploaded) with a placeholder hash; /complete
    # fills in size + real hash once the bytes are in storage.
    db.add(Document(
        id=document_id,
        tenant_id=current_user.tenant_id,
        uploaded_by=current_user.id,
        filename=body.filename,
        file_type=file_type,
        storage_path=storage_key,
        content_hash=f"pending-{document_id}",
        status=DocumentStatus.uploaded,
    ))
    await db.commit()

    loop = asyncio.get_running_loop()
    if body.multipart:
        upload_id = await loop.run_in_executor(
            None, lambda: object_store.create_multipart_upload(storage_key, ctype)
        )
        return UploadInitResponse(document_id=document_id, storage_key=storage_key,
                                  method="multipart", upload_id=upload_id)
    url = await loop.run_in_executor(
        None, lambda: object_store.presigned_upload_url(storage_key, ctype)
    )
    return UploadInitResponse(document_id=document_id, storage_key=storage_key,
                              method="single", upload_url=url)


@router.post("/{document_id}/multipart/sign-part", response_model=SignPartResponse)
async def sign_part(
    document_id: str,
    body: SignPartRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store_dep),
):
    doc = await _owned_pending_doc(db, current_user.tenant_id, document_id)
    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        None, lambda: object_store.presigned_upload_part_url(doc.storage_path, body.upload_id, body.part_number)
    )
    return SignPartResponse(url=url)


@router.post("/{document_id}/multipart/abort", status_code=204)
async def abort_upload(
    document_id: str,
    body: AbortUploadRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store_dep),
):
    doc = await _owned_pending_doc(db, current_user.tenant_id, document_id)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: object_store.abort_multipart_upload(doc.storage_path, body.upload_id))
    await db.delete(doc)
    await db.commit()


@router.post("/{document_id}/complete", response_model=DocumentResponse)
async def complete_upload(
    document_id: str,
    body: CompleteUploadRequest,
    request: Request,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store_dep),
):
    doc = await _owned_pending_doc(db, current_user.tenant_id, document_id)
    loop = asyncio.get_running_loop()

    # Finalize a multipart upload if the client used one.
    if body.upload_id and body.parts:
        await loop.run_in_executor(
            None, lambda: object_store.complete_multipart_upload(doc.storage_path, body.upload_id, body.parts)
        )

    # Verify the object actually landed in storage + get its size.
    try:
        head = await loop.run_in_executor(None, lambda: object_store.head_object(doc.storage_path))
    except Exception:
        raise HTTPException(status_code=400, detail="Upload not found in storage — finish uploading before completing.")

    # Content scan: reject a payload whose magic bytes don't match the extension.
    head_bytes = await loop.run_in_executor(None, lambda: object_store.read_range(doc.storage_path, 512))
    ok, sniffed = content_matches(head_bytes, doc.file_type)
    if not ok:
        doc.status = DocumentStatus.rejected_security
        doc.failure_reason = f"content scan: sniffed {sniffed!r} does not match declared {doc.file_type}"
        await loop.run_in_executor(None, lambda: object_store.delete(doc.storage_path))
        await db.commit()
        raise HTTPException(status_code=422, detail=f"File rejected — content ({sniffed}) does not match a {doc.file_type}.")

    # Deduplicate by ETag (single-part ETag == MD5 of content).
    etag = head["etag"]
    if etag:
        dup = (await db.execute(
            select(Document).where(
                Document.tenant_id == current_user.tenant_id,
                Document.content_hash == etag,
                Document.id != document_id,
            )
        )).scalar_one_or_none()
        if dup:
            await loop.run_in_executor(None, lambda: object_store.delete(doc.storage_path))
            await db.delete(doc)
            await db.commit()
            return DocumentResponse(document_id=dup.id, status=dup.status.value,
                                    filename=dup.filename, message="Duplicate document — already uploaded.")

    doc.content_hash = etag or f"nohash-{document_id}"
    doc.file_size_bytes = head["size"]
    db.add(AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="document_upload",
        resource_type="document",
        resource_id=document_id,
        log_metadata={"filename": doc.filename, "file_type": doc.file_type,
                      "size": head["size"], "direct": True, **_req_meta(request)},
    ))
    await db.commit()

    _enqueue_ingestion(document_id, current_user.tenant_id, doc.storage_path, doc.file_type,
                       current_user.collection_tags, current_user.role.value)
    return DocumentResponse(document_id=document_id, status=DocumentStatus.uploaded.value,
                            filename=doc.filename, message="Upload complete; queued for processing.")


@router.get("/", response_model=list[DocumentListItem])
async def list_documents(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
    folder_id: str | None = None,   # a folder id, or "unfiled" for documents with no folder
):
    stmt = select(Document).where(Document.tenant_id == current_user.tenant_id)
    if folder_id == "unfiled":
        stmt = stmt.where(Document.folder_id.is_(None))
    elif folder_id:
        stmt = stmt.where(Document.folder_id == folder_id)
    result = await db.execute(
        stmt.offset(skip).limit(limit).order_by(Document.created_at.desc())
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
            folder_id=d.folder_id,
        )
        for d in docs
    ]


@router.patch("/{document_id}/folder", response_model=DocumentListItem)
async def move_document(
    document_id: str,
    body: MoveFolderRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    """Move a document into a folder (or unfile it with folder_id=null)."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == current_user.tenant_id
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if body.folder_id is not None:
        f = await db.execute(
            select(Folder).where(
                Folder.id == body.folder_id, Folder.tenant_id == current_user.tenant_id
            )
        )
        if f.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Folder not found")

    doc.folder_id = body.folder_id
    await db.commit()
    await db.refresh(doc)
    return DocumentListItem(
        document_id=doc.id,
        filename=doc.filename,
        file_type=doc.file_type,
        status=doc.status.value,
        page_count=doc.page_count,
        created_at=doc.created_at.isoformat(),
        folder_id=doc.folder_id,
    )


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
        folder_id=doc.folder_id,
    )


# Statuses at which ingestion is finished (success or failure) — the SSE stream
# emits a final event and closes once one of these is reached.
_TERMINAL_STATUSES = {
    DocumentStatus.ready,
    DocumentStatus.ready_with_warnings,
    DocumentStatus.failed_retryable,
    DocumentStatus.failed_terminal,
    DocumentStatus.rejected_security,
    DocumentStatus.quota_exceeded,
}


@router.get("/{document_id}/events")
async def stream_document_events(
    document_id: str,
    current_user: User = Depends(require_viewer),
):
    """Server-Sent Events stream of live ingestion progress for one document.

    Polls the document's status (updated by the worker at every stage:
    parsing → chunking → embedding → indexing → ready) and emits a `status`
    event whenever it changes, then a `done` event once a terminal status is
    reached. Closes automatically — clients should reconnect only for docs that
    are still in progress.
    """
    tenant_id = current_user.tenant_id

    async def event_generator():
        last_status: str | None = None
        seq = 0
        # Hard cap so a stuck ingestion can't hold the connection forever.
        for _ in range(600):  # 600 * 1s ≈ 10 min
            async with AsyncSessionLocal() as db:
                row = await db.execute(
                    select(Document.status, Document.failure_reason).where(
                        Document.id == document_id,
                        Document.tenant_id == tenant_id,
                    )
                )
                rec = row.first()

            if rec is None:
                yield _doc_event("error", {"message": "Document not found"}, seq)
                return

            status, failure_reason = rec
            status_value = status.value

            if status_value != last_status:
                seq += 1
                yield _doc_event(
                    "status",
                    {"document_id": document_id, "status": status_value,
                     "failure_reason": failure_reason},
                    seq,
                )
                last_status = status_value

            if status in _TERMINAL_STATUSES:
                seq += 1
                yield _doc_event("done", {"document_id": document_id, "status": status_value}, seq)
                return

            await asyncio.sleep(1.0)

        # Timed out without reaching a terminal state.
        yield _doc_event("done", {"document_id": document_id, "status": last_status, "timeout": True}, seq + 1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _doc_event(event_type: str, data: dict, seq: int) -> str:
    return f"data: {json.dumps({'event_type': event_type, 'seq': seq, **data})}\n\n"


@router.get("/{document_id}/view-url")
async def get_document_view_url(
    document_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    object_store: ObjectStore = Depends(get_object_store_dep),
):
    """Return a short-lived presigned URL to view/download the original file."""
    import asyncio
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.tenant_id == current_user.tenant_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    loop = asyncio.get_running_loop()
    url = await loop.run_in_executor(
        None,
        lambda: object_store.presigned_download_url(doc.storage_path, expires_in=900),
    )
    return {"url": url, "filename": doc.filename, "file_type": doc.file_type}


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    request: Request,
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
    db.add(AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="document_delete",
        resource_type="document",
        resource_id=document_id,
        log_metadata={"filename": doc.filename, **_req_meta(request)},
    ))
    await db.delete(doc)
    await db.commit()
