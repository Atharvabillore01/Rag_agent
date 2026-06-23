from typing import AsyncIterator
from openai import AsyncOpenAI

from src.providers.base import LLMProvider, Message, CompletionResponse

_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OllamaProvider(LLMProvider):
    """
    Ollama exposes an OpenAI-compatible endpoint at /v1.
    api_key is required by the SDK but unused by Ollama — pass any string.
    """

    def __init__(self, model: str, base_url: str = _DEFAULT_BASE_URL):
        self._model = model
        self._client = AsyncOpenAI(api_key="ollama", base_url=base_url)

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
        return CompletionResponse(
            content=resp.choices[0].message.content or "",
            model=resp.model,
            provider="ollama",
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
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
