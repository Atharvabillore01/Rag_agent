"""Google Gemini provider (text + vision) via the google-genai SDK.

Gemini Flash is a strong, low-cost multimodal model — a good default for the
`vision` task (OCR of scanned / complex documents), the `translate` task, and a
cheap option for `extract`. The SDK is imported lazily in __init__ so the
provider factory imports fine even where google-genai isn't installed;
instantiating without it raises a clear install hint.
"""

from typing import AsyncIterator

from src.providers.base import CompletionResponse, LLMProvider, Message

# Anthropic/OpenAI use "assistant"; Gemini uses "model".
_ROLE_MAP = {"assistant": "model", "user": "user"}


class GeminiProvider(LLMProvider):
    supports_vision = True

    def __init__(self, api_key: str, model: str):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - only when dep missing
            raise ImportError(
                "google-genai is not installed. Run `pip install google-genai` "
                "to use the 'gemini' provider."
            ) from exc
        self._types = types
        self._model = model
        self._client = genai.Client(api_key=api_key)

    def _split(self, messages: list[Message]):
        """Return (system_instruction, contents) in Gemini's shape."""
        system = next((m.content for m in messages if m.role == "system"), None)
        contents = [
            self._types.Content(
                role=_ROLE_MAP.get(m.role, "user"),
                parts=[self._types.Part.from_text(text=m.content)],
            )
            for m in messages
            if m.role != "system"
        ]
        return system, contents

    def _config(self, *, system, max_tokens, temperature, json_mode):
        return self._types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system,
            response_mime_type="application/json" if json_mode else None,
        )

    @staticmethod
    def _usage(resp):
        um = getattr(resp, "usage_metadata", None)
        return (
            getattr(um, "prompt_token_count", 0) or 0,
            getattr(um, "candidates_token_count", 0) or 0,
        )

    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> CompletionResponse:
        system, contents = self._split(messages)
        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=self._config(system=system, max_tokens=max_tokens, temperature=temperature, json_mode=json_mode),
        )
        pin, pout = self._usage(resp)
        return CompletionResponse(
            content=resp.text or "", model=self._model, provider="gemini",
            input_tokens=pin, output_tokens=pout,
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        system, contents = self._split(messages)
        stream = await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=contents,
            config=self._config(system=system, max_tokens=max_tokens, temperature=temperature, json_mode=False),
        )
        async for chunk in stream:
            if getattr(chunk, "text", None):
                yield chunk.text

    async def complete_with_images(
        self,
        prompt: str,
        images: list[bytes],
        *,
        system: str | None = None,
        mime: str = "image/png",
        max_tokens: int = 2048,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> CompletionResponse:
        parts = [self._types.Part.from_text(text=prompt)]
        parts.extend(self._types.Part.from_bytes(data=img, mime_type=mime) for img in images)
        contents = [self._types.Content(role="user", parts=parts)]
        resp = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=self._config(system=system, max_tokens=max_tokens, temperature=temperature, json_mode=json_mode),
        )
        pin, pout = self._usage(resp)
        return CompletionResponse(
            content=resp.text or "", model=self._model, provider="gemini",
            input_tokens=pin, output_tokens=pout,
        )
