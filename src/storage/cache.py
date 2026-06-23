"""Redis cache wrapper — rate limiting, query cache, stream replay buffer (§4.3, §7.2, §8.2)."""

import hashlib
import json
from functools import lru_cache

import redis.asyncio as aioredis

from src.config import get_settings


class CacheClient:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis

    # ── Query cache ───────────────────────────────────────────────────────────

    @staticmethod
    def _query_cache_key(tenant_id: str, query: str, collection_tags: list[str] | None) -> str:
        tag_str = ",".join(sorted(collection_tags or []))
        digest = hashlib.sha256(f"{tenant_id}:{query}:{tag_str}".encode()).hexdigest()
        return f"qcache:{digest}"

    async def get_query_cache(self, tenant_id: str, query: str, collection_tags: list[str] | None) -> dict | None:
        key = self._query_cache_key(tenant_id, query, collection_tags)
        raw = await self._r.get(key)
        return json.loads(raw) if raw else None

    async def set_query_cache(
        self,
        tenant_id: str,
        query: str,
        collection_tags: list[str] | None,
        value: dict,
        ttl: int,
    ) -> None:
        key = self._query_cache_key(tenant_id, query, collection_tags)
        await self._r.setex(key, ttl, json.dumps(value))

    # ── Rate limiting — sliding window (§21) ─────────────────────────────────

    # Lua script: atomically INCR and set TTL on first touch.
    # Without atomicity, a crash between INCR and EXPIRE leaves a key with no
    # TTL that persists forever — effectively banning the tenant permanently.
    _RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

    async def rate_limit_check(
        self, key: str, max_count: int, window_seconds: int
    ) -> tuple[bool, int]:
        """Returns (allowed, current_count). Atomically INCR + conditionally EXPIRE."""
        current = int(await self._r.eval(self._RATE_LIMIT_LUA, 1, key, window_seconds))
        return current <= max_count, current

    async def get_rate_limit_count(self, key: str) -> int:
        val = await self._r.get(key)
        return int(val) if val else 0

    # ── Demo quota — fast counter in Redis, Postgres is source of truth ───────

    async def incr_demo_queries(self, tenant_id: str) -> int:
        key = f"demo:qpd:{tenant_id}"
        count = await self._r.incr(key)
        if count == 1:
            # Expire at midnight — set TTL to end of day (86400s max)
            await self._r.expire(key, 86400)
        return int(count)

    async def get_demo_queries_today(self, tenant_id: str) -> int:
        val = await self._r.get(f"demo:qpd:{tenant_id}")
        return int(val) if val else 0

    async def reset_demo_queries(self, tenant_id: str) -> None:
        await self._r.delete(f"demo:qpd:{tenant_id}")

    # ── Stream event replay buffer (§8.2) ────────────────────────────────────

    async def push_stream_event(self, query_id: str, event: dict, ttl: int) -> None:
        key = f"stream:{query_id}"
        await self._r.rpush(key, json.dumps(event))
        await self._r.expire(key, ttl)

    async def get_stream_events(self, query_id: str, after_seq: int = 0) -> list[dict]:
        key = f"stream:{query_id}"
        raw_events = await self._r.lrange(key, after_seq, -1)
        return [json.loads(e) for e in raw_events]

    # ── Document status cache — avoids Postgres hit on every query ─────────

    async def set_document_status(self, tenant_id: str, document_id: str, status: str) -> None:
        key = f"docstatus:{tenant_id}:{document_id}"
        await self._r.setex(key, 300, status)  # 5-min TTL, re-fetched from DB after

    async def get_document_status(self, tenant_id: str, document_id: str) -> str | None:
        val = await self._r.get(f"docstatus:{tenant_id}:{document_id}")
        return val.decode() if val else None

    # ── Generic helpers ───────────────────────────────────────────────────────

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def ping(self) -> bool:
        try:
            return await self._r.ping()
        except Exception:
            return False


@lru_cache(maxsize=1)
def _get_redis() -> aioredis.Redis:
    s = get_settings()
    return aioredis.from_url(s.redis_url, decode_responses=True)


@lru_cache(maxsize=1)
def get_cache() -> CacheClient:
    return CacheClient(_get_redis())
