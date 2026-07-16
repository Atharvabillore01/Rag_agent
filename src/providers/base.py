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

    # Providers that accept image input (for OCR / document vision) set this True
    # and implement complete_with_images. Callers can gate on it to pick a
    # vision-capable model for the "vision" task (see providers.factory).
    supports_vision: bool = False

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
        """Answer a prompt about one or more images (OCR / document vision).

        Default raises — only vision-capable providers override it. Used by the
        vision-OCR pipeline (feature-implementation-plan Feature 5); the routing
        layer sends the "vision" task to a provider where supports_vision is True.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support image input. Route the "
            f"'vision' task to a vision-capable provider (e.g. gemini, openai, openai_compatible)."
        )

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
