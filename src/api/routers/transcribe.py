"""Voice-input transcription endpoint (feature-implementation-plan §24)."""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.auth import require_viewer
from src.db.models import User
from src.providers.stt import transcribe_audio

router = APIRouter(prefix="/transcribe", tags=["transcribe"])
logger = logging.getLogger(__name__)

_ALLOWED = {".mp3", ".wav", ".m4a", ".webm", ".ogg", ".mp4", ".aiff", ".flac", ".mpeg", ".mpga"}
_MAX_BYTES = 25 * 1024 * 1024  # 25 MB


class TranscriptionResponse(BaseModel):
    text: str


@router.post("/", response_model=TranscriptionResponse)
async def transcribe(
    file: UploadFile = File(...),
    current_user: User = Depends(require_viewer),
):
    filename = file.filename or "audio.webm"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"Unsupported audio type {ext!r}.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="Audio exceeds the 25 MB limit.")

    try:
        text = await transcribe_audio(data, filename)
    except Exception as exc:  # noqa: BLE001 — don't leak provider internals
        logger.error("transcription failed for tenant=%s: %s", current_user.tenant_id, exc, exc_info=exc)
        raise HTTPException(status_code=502, detail="Transcription failed. Please try again.")
    return TranscriptionResponse(text=text)
