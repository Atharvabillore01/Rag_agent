from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.providers.base import LLMProvider, EmbedProvider, RerankProvider


# ---------------------------------------------------------------------------
# Settings — all values read from environment / .env file
# ---------------------------------------------------------------------------

class ProviderSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM (base defaults) ---
    llm_provider: str = "groq"                          # groq | openai | azure_openai | claude | ollama | gemini | openai_compatible | huggingface
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

    # Gemini (Google) — strong, low-cost multimodal; good for vision/translate.
    google_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Generic OpenAI-compatible endpoint — Together / Fireworks / OpenRouter /
    # DeepInfra / vLLM / LM Studio / your own fine-tuned model server.
    openai_compatible_base_url: str = ""
    openai_compatible_api_key: str = ""
    openai_compatible_model: str = ""

    # Hugging Face Inference (OpenAI-compatible router) — hosted open models.
    hf_api_key: str = ""
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_model: str = ""

    # ── Per-task model routing (feature-implementation-plan §5) ───────────────
    # Each is optional. An empty provider falls back to `llm_provider`; an empty
    # model falls back to that provider's default (or `llm_model`). So with only
    # the base provider configured, every task behaves exactly as before.
    llm_route_provider: str = ""
    llm_extract_provider: str = ""
    llm_extract_model: str = ""
    llm_draft_provider: str = ""
    llm_draft_model: str = ""
    llm_vision_provider: str = ""
    llm_vision_model: str = ""
    llm_translate_provider: str = ""
    llm_translate_model: str = ""
    llm_verify_provider: str = ""
    llm_verify_model: str = ""


# ---------------------------------------------------------------------------
# Task identifiers — each maps to a (provider, model) via _resolve_task().
# ---------------------------------------------------------------------------

class LLMTask:
    DEFAULT = "default"      # main agent reasoning / generation
    ROUTE = "route"          # cheap intent routing / classification
    EXTRACT = "extract"      # structured extraction (Parallel Review, field pull)
    DRAFT = "draft"          # long-form document generation
    VISION = "vision"        # OCR / image + document understanding
    TRANSLATE = "translate"  # translation
    VERIFY = "verify"        # independent cross-check of another model's output


# task -> (provider_setting_field, model_setting_field). None means "no override
# field for this dimension — use the base value".
_TASK_OVERRIDES: dict[str, tuple[str | None, str | None]] = {
    LLMTask.DEFAULT:   (None, None),
    LLMTask.ROUTE:     ("llm_route_provider", "llm_router_model"),
    LLMTask.EXTRACT:   ("llm_extract_provider", "llm_extract_model"),
    LLMTask.DRAFT:     ("llm_draft_provider", "llm_draft_model"),
    LLMTask.VISION:    ("llm_vision_provider", "llm_vision_model"),
    LLMTask.TRANSLATE: ("llm_translate_provider", "llm_translate_model"),
    LLMTask.VERIFY:    ("llm_verify_provider", "llm_verify_model"),
}


def _provider_default_model(provider: str, s: ProviderSettings) -> str:
    """Default model for a provider when a task selects the provider but no model."""
    return {
        "gemini": s.gemini_model,
        "openai_compatible": s.openai_compatible_model,
        "huggingface": s.hf_model,
    }.get(provider) or s.llm_model


def _resolve_task(s: ProviderSettings, task: str) -> tuple[str, str]:
    """Resolve a task to a concrete (provider, model)."""
    prov_field, model_field = _TASK_OVERRIDES.get(task, (None, None))
    task_provider = getattr(s, prov_field) if prov_field else ""
    task_model = getattr(s, model_field) if model_field else ""
    base_model = s.llm_router_model if task == LLMTask.ROUTE else s.llm_model

    provider = task_provider or s.llm_provider
    if task_model:
        model = task_model
    elif task_provider:
        # Task picked a different provider but no model — use that provider's default.
        model = _provider_default_model(task_provider, s)
    else:
        model = base_model
    return provider, model


# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------

def _build_provider(provider: str, model: str, s: ProviderSettings) -> LLMProvider:
    match provider:
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

        case "gemini":
            from src.providers.llm.gemini import GeminiProvider
            return GeminiProvider(api_key=s.google_api_key, model=model or s.gemini_model)

        case "openai_compatible":
            from src.providers.llm.openai_compatible import OpenAICompatibleProvider
            return OpenAICompatibleProvider(
                api_key=s.openai_compatible_api_key,
                model=model or s.openai_compatible_model,
                base_url=s.openai_compatible_base_url,
                provider_label="openai_compatible",
            )

        case "huggingface":
            from src.providers.llm.openai_compatible import OpenAICompatibleProvider
            return OpenAICompatibleProvider(
                api_key=s.hf_api_key,
                model=model or s.hf_model,
                base_url=s.hf_base_url,
                provider_label="huggingface",
            )

        case _:
            raise ValueError(
                f"Unknown LLM provider: '{provider}'. Valid options: groq, openai, "
                f"azure_openai, claude, ollama, gemini, openai_compatible, huggingface"
            )


# ---------------------------------------------------------------------------
# Public factory functions
# ---------------------------------------------------------------------------

def get_llm_for_task(
    task: str = LLMTask.DEFAULT,
    *,
    settings: ProviderSettings | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> LLMProvider:
    """Return the LLM provider configured for a task.

    Resolution order: an explicit per-call/tenant override (provider/model) wins;
    otherwise the task's configured provider+model; otherwise the base defaults.
    """
    s = settings or ProviderSettings()
    if provider_override or model_override:
        provider = provider_override or s.llm_provider
        model = model_override or s.llm_model
        return _build_provider(provider, model, s)
    provider, model = _resolve_task(s, task)
    return _build_provider(provider, model, s)


def get_llm_provider(
    settings: ProviderSettings | None = None,
    *,
    router: bool = False,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> LLMProvider:
    """Backward-compatible entry point. `router=True` selects the route task."""
    return get_llm_for_task(
        LLMTask.ROUTE if router else LLMTask.DEFAULT,
        settings=settings,
        provider_override=provider_override,
        model_override=model_override,
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
                f"Unknown rerank provider: '{s.rerank_provider}'. Valid options: local"
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


@lru_cache(maxsize=16)
def task_llm(task: str) -> LLMProvider:
    """Cached provider for a task (default/route/extract/draft/vision/translate/verify)."""
    return get_llm_for_task(task)


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


def get_tenant_task_llm(
    task: str,
    provider_override: str | None,
    model_override: str | None,
) -> LLMProvider:
    """Provider for a task, honoring a tenant's explicit override first.

    A tenant that has pinned its own provider/model gets that for every task;
    otherwise the task's routed model (task_llm) is used.
    """
    if provider_override or model_override:
        return get_tenant_llm(provider_override, model_override)
    return task_llm(task)
