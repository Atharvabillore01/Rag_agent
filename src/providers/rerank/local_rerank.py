import asyncio
import os
from functools import lru_cache

# HuggingFace's Xet transfer backend hangs on some networks, stalling both model
# downloads and the on-load update check. Force plain HTTP. Must be set before
# sentence_transformers / huggingface_hub is imported (done lazily in _load_model).
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from src.providers.base import RerankProvider, RerankResult

_DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"


@lru_cache(maxsize=1)
def _load_model(model_name: str):
    from sentence_transformers import CrossEncoder
    return CrossEncoder(model_name)


class LocalRerankProvider(RerankProvider):
    """
    Cross-encoder reranking running fully locally.
    bge-reranker-v2-m3 is competitive with commercial rerankers on English.
    Runs on CPU but faster on GPU.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL):
        self._model_name = model_name

    async def rerank(
        self,
        query: str,
        candidates: list[str],
        top_n: int = 5,
    ) -> list[RerankResult]:
        if not candidates:
            return []

        pairs = [(query, c) for c in candidates]
        loop = asyncio.get_running_loop()

        scores: list[float] = await loop.run_in_executor(
            None,
            lambda: _load_model(self._model_name).predict(pairs).tolist(),
        )

        ranked = sorted(
            [RerankResult(index=i, score=scores[i], text=candidates[i]) for i in range(len(candidates))],
            key=lambda r: r.score,
            reverse=True,
        )
        return ranked[:top_n]
