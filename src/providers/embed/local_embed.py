import asyncio
from functools import lru_cache

from src.providers.base import EmbedProvider, EmbedResponse

_DEFAULT_MODEL = "BAAI/bge-large-en-v1.5"


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


class LocalEmbedProvider(EmbedProvider):
    """
    sentence-transformers embed running fully locally — no API key, no cost.
    Model is loaded once and cached. First call is slow (model download + load);
    subsequent calls are fast.

    Recommended models:
      - BAAI/bge-large-en-v1.5   (1024 dims, best quality, ~1.3 GB)
      - BAAI/bge-base-en-v1.5    (768 dims, smaller, faster)
      - nomic-ai/nomic-embed-text-v1  (768 dims, good quality)
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        self._model_name = model_name

    async def embed(self, texts: list[str]) -> EmbedResponse:
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: _load_model(self._model_name).encode(texts, normalize_embeddings=True).tolist(),
        )
        return EmbedResponse(
            embeddings=embeddings,
            model=self._model_name,
            provider="local",
            tokens=sum(len(t.split()) for t in texts),  # approx
        )
