from typing import AsyncIterator
from anthropic import AsyncAnthropic

from src.providers.base import LLMProvider, Message, CompletionResponse


class ClaudeProvider(LLMProvider):
    """
    Anthropic's API separates the system message from the messages list.
    This provider extracts the first system-role message automatically.
    """

    def __init__(self, api_key: str, model: str):
        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)

    def _split_messages(self, messages: list[Message]):
        system = next((m.content for m in messages if m.role == "system"), None)
        user_msgs = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
        return system, user_msgs

    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> CompletionResponse:
        system, user_msgs = self._split_messages(messages)

        kwargs = {}
        if system:
            kwargs["system"] = system

        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=user_msgs,
            **kwargs,
        )
        return CompletionResponse(
            content=resp.content[0].text,
            model=resp.model,
            provider="claude",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        system, user_msgs = self._split_messages(messages)

        kwargs = {}
        if system:
            kwargs["system"] = system

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=user_msgs,
            **kwargs,
        ) as stream:
            async for text in stream.text_stream:
                yield text
