"""Generic OpenAI-compatible chat provider.

Points the OpenAI SDK at ANY OpenAI-compatible endpoint via `base_url`. This is
the single seam through which open-source and *fine-tuned* models plug in —
anything that serves the OpenAI chat-completions API works unchanged:

  * Together AI, Fireworks, OpenRouter, DeepInfra  (hosted open models)
  * Hugging Face Inference (router.huggingface.co/v1) / a dedicated TGI endpoint
  * vLLM / LM Studio / llama.cpp server                (self-hosted, incl. your
    own fine-tunes on legal / CA corpora)

So "use an open-source HF model for task X" = host it behind an OpenAI-compatible
endpoint and route that task here (see providers.factory task routing).
"""

import base64
from typing import AsyncIterator

from openai import AsyncOpenAI

from src.providers.base import CompletionResponse, LLMProvider, Message


class OpenAICompatibleProvider(LLMProvider):
    # Vision works only if the *served model* is multimodal (e.g. Qwen2-VL,
    # Llama-3.2-Vision, GPT-4o). We expose the capability; the deployment picks
    # a model that honors it.
    supports_vision = True

    def __init__(self, api_key: str, model: str, base_url: str, provider_label: str = "openai_compatible"):
        if not base_url:
            raise ValueError(
                "OpenAICompatibleProvider requires a base_url (e.g. an "
                "OpenAI-compatible endpoint from Together/Fireworks/OpenRouter/HF/vLLM)."
            )
        self._model = model
        self._label = provider_label
        # api_key may be empty for a local unauthenticated server; send a
        # placeholder so the SDK doesn't error on a missing key.
        self._client = AsyncOpenAI(api_key=api_key or "not-needed", base_url=base_url)

    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> CompletionResponse:
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=self._to_openai_messages(messages),
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        usage = resp.usage
        return CompletionResponse(
            content=resp.choices[0].message.content or "",
            model=resp.model or self._model,
            provider=self._label,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=self._to_openai_messages(messages),
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

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
        content: list[dict] = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": content})

        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        usage = resp.usage
        return CompletionResponse(
            content=resp.choices[0].message.content or "",
            model=resp.model or self._model,
            provider=self._label,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
