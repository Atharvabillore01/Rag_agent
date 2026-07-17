"""Per-tenant rate-limit resolution (feature-implementation-plan §27).

Resolves the effective limits for a tenant from, in order of precedence:
  1. a short-lived Redis cache (`rlcfg:{tenant}`),
  2. the tenant's `RateLimitConfig` row,
  3. the platform defaults in settings.

Every path is fail-safe: a DB or Redis hiccup degrades to defaults rather than
500-ing the request being metered. This is what makes `RateLimitConfig` a live
control instead of dead config (it finishes G8).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from sqlalchemy import select

from src.config import get_settings
from src.db.models import RateLimitConfig
from src.db.session import AsyncSessionLocal
from src.storage.cache import get_cache

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class TenantLimits:
    qpm: int
    qpd: int
    ingestion_per_hour: int
    max_concurrent: int


def default_limits() -> TenantLimits:
    return TenantLimits(
        qpm=settings.rate_limit_default_qpm,
        qpd=settings.rate_limit_default_qpd,
        ingestion_per_hour=settings.rate_limit_default_ingestion_per_hour,
        max_concurrent=settings.rate_limit_default_max_concurrent,
    )


async def resolve_tenant_limits(tenant_id: str) -> TenantLimits:
    """Effective limits for ``tenant_id`` (cache → DB row → defaults)."""
    if not tenant_id:
        return default_limits()

    cache = get_cache()
    cached = await cache.get_tenant_limits(tenant_id)
    if cached:
        try:
            return TenantLimits(**cached)
        except (TypeError, ValueError):
            pass  # malformed cache entry -> re-resolve below

    limits = default_limits()
    try:
        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(RateLimitConfig).where(RateLimitConfig.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()
            if row is not None:
                limits = TenantLimits(
                    qpm=row.queries_per_minute,
                    qpd=row.queries_per_day,
                    ingestion_per_hour=row.ingestion_per_hour,
                    max_concurrent=row.max_concurrent_queries,
                )
    except Exception as exc:  # noqa: BLE001 — never let limit resolution break the request
        logger.warning("resolve_tenant_limits falling back to defaults for %s: %s", tenant_id, exc)
        return limits

    await cache.set_tenant_limits(tenant_id, asdict(limits), ttl=settings.rate_limit_config_cache_seconds)
    return limits


async def invalidate_tenant_limits(tenant_id: str) -> None:
    """Drop the cached limits so the next resolve reflects a fresh DB value."""
    await get_cache().invalidate_tenant_limits(tenant_id)
