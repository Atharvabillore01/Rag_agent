from openai import AsyncOpenAI

from src.providers.base import EmbedProvider, EmbedResponse

_DEFAULT_BASE_URL = "http://localhost:11434/v1"


class OllamaEmbedProvider(EmbedProvider):

    def __init__(self, model: str = "nomic-embed-text", base_url: str = _DEFAULT_BASE_URL):
        self._model_name = model
        self._client = AsyncOpenAI(api_key="ollama", base_url=base_url)

    async def embed(self, texts: list[str]) -> EmbedResponse:
        resp = await self._client.embeddings.create(model=self._model_name, input=texts)
        return EmbedResponse(
            embeddings=[d.embedding for d in resp.data],
            model=self._model_name,
            provider="ollama",
            tokens=resp.usage.total_tokens if resp.usage else 0,
        )
