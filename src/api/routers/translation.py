"""Document translation endpoints (feature-implementation-plan §9).

Translate a document's text into a target language, routed through the
`translate` task (Groq now; Gemini / an open IndicTrans2 model later via env).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_editor, require_viewer
from src.db.models import Translation, User
from src.db.session import get_db
from src.export.docx import DOCX_MEDIA, docx_filename, translation_to_docx
from src.providers.factory import LLMTask, get_tenant_task_llm
from src.review.loader import load_document_texts
from src.translation.engine import translate_text

router = APIRouter(prefix="/translation", tags=["translation"])
logger = logging.getLogger(__name__)


class CreateTranslationRequest(BaseModel):
    document_id: str = Field(min_length=1)
    target_language: str = Field(min_length=1, max_length=80)


class TranslationSummary(BaseModel):
    id: str
    document_id: str
    filename: str | None
    target_language: str
    status: str
    created_at: str


class TranslationDetail(BaseModel):
    id: str
    document_id: str
    filename: str | None
    target_language: str
    status: str
    result: str | None
    created_at: str
    updated_at: str


def _detail(t: Translation) -> TranslationDetail:
    return TranslationDetail(
        id=t.id,
        document_id=t.document_id,
        filename=t.filename,
        target_language=t.target_language,
        status=t.status,
        result=t.result,
        created_at=t.created_at.isoformat(),
        updated_at=t.updated_at.isoformat(),
    )


async def _get_owned(db: AsyncSession, tenant_id: str, translation_id: str) -> Translation:
    res = await db.execute(
        select(Translation).where(
            Translation.id == translation_id, Translation.tenant_id == tenant_id
        )
    )
    t = res.scalar_one_or_none()
    if t is None:
        raise HTTPException(404, detail="Translation not found")
    return t


@router.post("/", response_model=TranslationDetail, status_code=201)
async def create_translation(
    body: CreateTranslationRequest,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    docs, missing, not_ready = await load_document_texts(
        db, current_user.tenant_id, [body.document_id]
    )
    if missing:
        raise HTTPException(404, detail=f"Document not found: {missing}")
    if not_ready:
        raise HTTPException(400, detail=f"Document still processing (not ready): {not_ready}")

    _, filename, text = docs[0]
    if not text.strip():
        raise HTTPException(400, detail="Document has no extractable text to translate.")

    llm = get_tenant_task_llm(LLMTask.TRANSLATE, None, None)
    result = await translate_text(llm, text, body.target_language)

    translation = Translation(
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
        document_id=body.document_id,
        filename=filename,
        target_language=body.target_language,
        result=result,
        status="complete",
    )
    db.add(translation)
    await db.commit()
    await db.refresh(translation)
    logger.info(
        "translation created",
        extra={"translation_id": translation.id, "tenant_id": current_user.tenant_id,
               "target_language": body.target_language},
    )
    return _detail(translation)


@router.get("/", response_model=list[TranslationSummary])
async def list_translations(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    res = await db.execute(
        select(Translation)
        .where(Translation.tenant_id == current_user.tenant_id)
        .order_by(Translation.created_at.desc())
        .offset(skip)
        .limit(min(limit, 100))
    )
    return [
        TranslationSummary(
            id=t.id,
            document_id=t.document_id,
            filename=t.filename,
            target_language=t.target_language,
            status=t.status,
            created_at=t.created_at.isoformat(),
        )
        for t in res.scalars().all()
    ]


@router.get("/{translation_id}", response_model=TranslationDetail)
async def get_translation(
    translation_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    return _detail(await _get_owned(db, current_user.tenant_id, translation_id))


@router.get("/{translation_id}/export")
async def export_translation(
    translation_id: str,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_owned(db, current_user.tenant_id, translation_id)
    data = translation_to_docx(t.filename, t.target_language, t.result)
    name = f"{t.filename or 'document'}_{t.target_language or ''}"
    return Response(
        content=data,
        media_type=DOCX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{docx_filename(name)}"'},
    )


@router.delete("/{translation_id}", status_code=204)
async def delete_translation(
    translation_id: str,
    current_user: User = Depends(require_editor),
    db: AsyncSession = Depends(get_db),
):
    t = await _get_owned(db, current_user.tenant_id, translation_id)
    await db.delete(t)
    await db.commit()
