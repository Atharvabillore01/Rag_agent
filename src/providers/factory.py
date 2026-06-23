from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.providers.base import LLMProvider, EmbedProvider, RerankProvider


# ---------------------------------------------------------------------------
# Settings — all values read from environment / .env file
# ---------------------------------------------------------------------------

class ProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---
    llm_provider: str = "groq"                          # groq | openai | azure_openai | claude | ollama
    llm_model: str = "llama-3.3-70b-versatile"          # main agent/generation model
    llm_router_model: str = "llama-3.1-8b-instant"      # cheap model for intent routing / classification

    # --- Embed ---
    embed_provider: str = "local"                       # local | ollama | openai
    embed_model: str = "BAAI/bge-large-en-v1.5"

    # --- Rerank ---
    rerank_provider: str = "local"                      # local (only option for now)
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    # --- Provider credentials ---
    groq_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Azure OpenAI
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""                     # https://YOUR-RESOURCE.openai.azure.com/
    azure_openai_deployment: str = ""                   # deployment name in Azure portal
    azure_openai_api_version: str = "2024-02-01"

    # Ollama
    ollama_base_url: str = "http://localhost:11434/v1"


# ---------------------------------------------------------------------------
# Factory functions
# ---------------------------------------------------------------------------

def get_llm_provider(
    settings: ProviderSettings | None = None,
    *,
    router: bool = False,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> LLMProvider:
    """
    Return the configured LLM provider.

    Args:
        settings:          override settings; uses env/.env if None
        router:            if True, use the cheaper router model instead of the main model
        provider_override: per-tenant override (stored in tenants.llm_provider_override)
        model_override:    per-tenant model override
    """
    s = settings or ProviderSettings()
    if provider_override:
        s = s.model_copy(update={"llm_provider": provider_override})
    if model_override:
        s = s.model_copy(update={"llm_model": model_override, "llm_router_model": model_override})
    model = s.llm_router_model if router else s.llm_model

    match s.llm_provider:
        case "groq":
            from src.providers.llm.groq import GroqProvider
            return GroqProvider(api_key=s.groq_api_key, model=model)

        case "openai":
            from src.providers.llm.openai_provider import OpenAIProvider
            return OpenAIProvider(api_key=s.openai_api_key, model=model)

        case "azure_openai":
            from src.providers.llm.azure_openai import AzureOpenAIProvider
            return AzureOpenAIProvider(
                api_key=s.azure_openai_api_key,
                endpoint=s.azure_openai_endpoint,
                deployment=s.azure_openai_deployment,
                api_version=s.azure_openai_api_version,
            )

        case "claude":
            from src.providers.llm.claude import ClaudeProvider
            return ClaudeProvider(api_key=s.anthropic_api_key, model=model)

        case "ollama":
            from src.providers.llm.ollama import OllamaProvider
            return OllamaProvider(model=model, base_url=s.ollama_base_url)

        case _:
            raise ValueError(
                f"Unknown LLM provider: '{s.llm_provider}'. "
                f"Valid options: groq, openai, azure_openai, claude, ollama"
            )


def get_embed_provider(settings: ProviderSettings | None = None) -> EmbedProvider:
    s = settings or ProviderSettings()

    match s.embed_provider:
        case "local":
            from src.providers.embed.local_embed import LocalEmbedProvider
            return LocalEmbedProvider(model_name=s.embed_model)

        case "ollama":
            from src.providers.embed.ollama_embed import OllamaEmbedProvider
            return OllamaEmbedProvider(model=s.embed_model, base_url=s.ollama_base_url)

        case "openai":
            from src.providers.embed.openai_embed import OpenAIEmbedProvider
            return OpenAIEmbedProvider(api_key=s.openai_api_key, model=s.embed_model)

        case _:
            raise ValueError(
                f"Unknown embed provider: '{s.embed_provider}'. "
                f"Valid options: local, ollama, openai"
            )


def get_rerank_provider(settings: ProviderSettings | None = None) -> RerankProvider:
    s = settings or ProviderSettings()

    match s.rerank_provider:
        case "local":
            from src.providers.rerank.local_rerank import LocalRerankProvider
            return LocalRerankProvider(model_name=s.rerank_model)

        case _:
            raise ValueError(
                f"Unknown rerank provider: '{s.rerank_provider}'. "
                f"Valid options: local"
            )


# ---------------------------------------------------------------------------
# Cached singletons — call these from FastAPI dependencies
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def llm() -> LLMProvider:
    return get_llm_provider()


@lru_cache(maxsize=1)
def router_llm() -> LLMProvider:
    return get_llm_provider(router=True)


@lru_cache(maxsize=1)
def embedder() -> EmbedProvider:
    return get_embed_provider()


@lru_cache(maxsize=1)
def reranker() -> RerankProvider:
    return get_rerank_provider()


# ---------------------------------------------------------------------------
# Per-tenant provider cache — keyed on (provider, model) so tenants sharing
# the same override get the same pooled client instance.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _tenant_llm_cached(provider: str, model: str) -> LLMProvider:
    return get_llm_provider(provider_override=provider, model_override=model)


def get_tenant_llm(
    provider_override: str | None,
    model_override: str | None,
) -> LLMProvider:
    """Return the LLM provider for a tenant, using overrides if configured.

    Falls back to the global singleton when no overrides are set so the common
    path is zero-cost (no extra object creation, same cached instance).
    """
    if not provider_override and not model_override:
        return llm()
    s = ProviderSettings()
    effective_provider = provider_override or s.llm_provider
    effective_model = model_override or s.llm_model
    return _tenant_llm_cached(effective_provider, effective_model)
