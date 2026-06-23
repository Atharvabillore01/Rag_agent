from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncGenerator, AsyncIterator


@dataclass
class Message:
    role: str   # "system" | "user" | "assistant"
    content: str


@dataclass
class CompletionResponse:
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class EmbedResponse:
    embeddings: list[list[float]]
    model: str
    provider: str
    tokens: int = 0


@dataclass
class RerankResult:
    index: int          # original index in candidates list
    score: float
    text: str


class LLMProvider(ABC):
    """All LLM calls go through this interface. Never import SDK clients directly in business logic."""

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        json_mode: bool = False,
    ) -> CompletionResponse: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> AsyncGenerator[str, None]: ...

    def _to_openai_messages(self, messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]


class EmbedProvider(ABC):
    @abstractmethod
    async def embed(self, texts: list[str]) -> EmbedResponse: ...


class RerankProvider(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[str],
        top_n: int = 5,
    ) -> list[RerankResult]: ...
