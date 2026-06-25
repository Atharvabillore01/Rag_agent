import asyncio
import os
from functools import lru_cache

# HuggingFace's Xet transfer backend (us.aws.cdn.hf.co/xet-bridge-us) hangs on
# some networks, stalling both model downloads and the on-load update check.
# Force plain HTTP, which is reliable. Must be set before sentence_transformers
# / huggingface_hub is imported (done lazily inside _load_model below).
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

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
