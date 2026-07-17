"""Speech-to-text (voice input) — feature-implementation-plan §24.

Transcribes audio via the configured provider's Whisper endpoint. Groq and
OpenAI both expose the OpenAI-compatible audio.transcriptions API, so one small
helper covers both (base_url is the only difference).
"""

from __future__ import annotations

from openai import AsyncOpenAI

from src.providers.factory import ProviderSettings

_GROQ_BASE = "https://api.groq.com/openai/v1"


async def transcribe_audio(
    data: bytes,
    filename: str = "audio.mp3",
    *,
    settings: ProviderSettings | None = None,
) -> str:
    """Return the transcript of the audio bytes."""
    s = settings or ProviderSettings()
    if s.stt_provider == "groq":
        client = AsyncOpenAI(api_key=s.groq_api_key, base_url=_GROQ_BASE)
    elif s.stt_provider == "openai":
        client = AsyncOpenAI(api_key=s.openai_api_key)
    else:
        raise ValueError(f"Unknown stt_provider: {s.stt_provider!r} (expected groq | openai)")

    resp = await client.audio.transcriptions.create(model=s.stt_model, file=(filename, data))
    return (resp.text or "").strip()
