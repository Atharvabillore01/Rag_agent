from openai import AsyncOpenAI

from src.providers.base import EmbedProvider, EmbedResponse


class OpenAIEmbedProvider(EmbedProvider):

    def __init__(self, api_key: str, model: str = "text-embedding-3-large"):
        self._model_name = model
        self._client = AsyncOpenAI(api_key=api_key)

    async def embed(self, texts: list[str]) -> EmbedResponse:
        resp = await self._client.embeddings.create(model=self._model_name, input=texts)
        return EmbedResponse(
            embeddings=[d.embedding for d in resp.data],
            model=resp.model,
            provider="openai",
            tokens=resp.usage.total_tokens,
        )
