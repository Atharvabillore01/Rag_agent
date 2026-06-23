from typing import AsyncIterator
from openai import AsyncAzureOpenAI

from src.providers.base import LLMProvider, Message, CompletionResponse


class AzureOpenAIProvider(LLMProvider):
    """
    Azure OpenAI uses deployment names instead of model names.
    The `deployment` param maps to what you named the deployment in Azure portal.
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str,       # e.g. https://YOUR-RESOURCE.openai.azure.com/
        deployment: str,     # the deployment name in Azure portal
        api_version: str = "2024-02-01",
    ):
        self._deployment = deployment
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )

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
            model=self._deployment,   # Azure uses deployment name here
            messages=self._to_openai_messages(messages),
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )
        return CompletionResponse(
            content=resp.choices[0].message.content or "",
            model=self._deployment,
            provider="azure_openai",
            input_tokens=resp.usage.prompt_tokens,
            output_tokens=resp.usage.completion_tokens,
        )

    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._deployment,
            messages=self._to_openai_messages(messages),
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
