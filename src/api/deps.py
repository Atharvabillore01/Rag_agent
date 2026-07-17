"""FastAPI dependency injection — shared resources (§15)."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_db
from src.storage.cache import CacheClient, get_cache
from src.storage.object import ObjectStore, get_object_store
from src.storage.vector import VectorStore, get_vector_store


async def resolve_task_llm(db: AsyncSession, tenant_id: str, task: str):
    """Return the LLM provider for ``task``, honoring the tenant's provider/model
    overrides (so confidential text is routed to the tenant's configured provider,
    not silently to the shared default). Mirrors the pattern in the review router."""
    from src.db.models import Tenant
    from src.providers.factory import get_tenant_task_llm

    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        return get_tenant_task_llm(task, None, None)
    return get_tenant_task_llm(task, tenant.llm_provider_override, tenant.llm_model_override)


def get_vector_store_dep() -> VectorStore:
    return get_vector_store()


def get_object_store_dep() -> ObjectStore:
    return get_object_store()


def get_cache_dep() -> CacheClient:
    return get_cache()
