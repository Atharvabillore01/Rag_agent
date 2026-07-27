"""Redis cache wrapper — rate limiting, query cache, stream replay buffer (§4.3, §7.2, §8.2)."""

import hashlib
import json
import logging
import time
from functools import lru_cache

import redis.asyncio as aioredis

from src.config import get_settings

logger = logging.getLogger(__name__)


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
        """Returns (allowed, current_count). Atomically INCR + conditionally EXPIRE.

        G20: if Redis is unavailable, FAIL OPEN (allow the request) rather than
        letting the outage 500 the endpoint — availability is preferred over
        strict rate limiting for a transient cache failure.
        """
        try:
            current = int(await self._r.eval(self._RATE_LIMIT_LUA, 1, key, window_seconds))
        except Exception as exc:  # noqa: BLE001 — Redis down/unreachable
            logger.warning("rate_limit_check failing open (Redis unavailable): %s", exc)
            return True, 0
        return current <= max_count, current

    async def get_rate_limit_count(self, key: str) -> int:
        """Current counter value, or 0 if unset. Fails SAFE (returns 0) on a Redis
        outage so read paths that surface usage (e.g. the platform console) degrade
        rather than 500."""
        try:
            val = await self._r.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_rate_limit_count failing safe (Redis unavailable): %s", exc)
            return 0
        return int(val) if val else 0

    # ── Demo quota — fast counter in Redis, Postgres is source of truth ───────

    # Same atomic INCR+EXPIRE pattern as rate limiting — avoids a key with no
    # TTL if the process crashes between the two calls.
    _DEMO_QUOTA_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""

    async def incr_demo_queries(self, tenant_id: str) -> int:
        key = f"demo:qpd:{tenant_id}"
        return int(await self._r.eval(self._DEMO_QUOTA_LUA, 1, key, 86400))

    async def get_demo_queries_today(self, tenant_id: str) -> int:
        val = await self._r.get(f"demo:qpd:{tenant_id}")
        return int(val) if val else 0

    async def incr_daily_queries(self, tenant_id: str) -> int:
        """G8: general per-tenant daily query counter (24h TTL). Returns the
        post-increment count so the caller can enforce a daily quota."""
        key = f"qpd:{tenant_id}"
        return int(await self._r.eval(self._DEMO_QUOTA_LUA, 1, key, 86400))

    async def incr_window(self, key: str, ttl: int) -> int:
        """Atomic INCR + first-touch EXPIRE for an arbitrary fixed-window counter
        (e.g. per-hour ingestion). Returns the post-increment count."""
        return int(await self._r.eval(self._DEMO_QUOTA_LUA, 1, key, ttl))

    # ── Per-tenant rate-limit config cache (§27) ─────────────────────────────
    # Avoids a Postgres read on every metered request; short TTL so an admin
    # change takes effect quickly even without explicit invalidation.

    async def get_tenant_limits(self, tenant_id: str) -> dict | None:
        """Cached per-tenant limits, or None on miss / Redis outage (fail-safe)."""
        try:
            raw = await self._r.get(f"rlcfg:{tenant_id}")
            return json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001
            logger.warning("get_tenant_limits miss (Redis unavailable): %s", exc)
            return None

    async def set_tenant_limits(self, tenant_id: str, limits: dict, ttl: int = 60) -> None:
        try:
            await self._r.setex(f"rlcfg:{tenant_id}", ttl, json.dumps(limits))
        except Exception as exc:  # noqa: BLE001
            logger.warning("set_tenant_limits failed (Redis unavailable): %s", exc)

    async def invalidate_tenant_limits(self, tenant_id: str) -> None:
        try:
            await self._r.delete(f"rlcfg:{tenant_id}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("invalidate_tenant_limits failed (Redis unavailable): %s", exc)

    # ── Concurrency limiter — self-healing sorted set (§27) ───────────────────
    # A ZSET of in-flight request members scored by start time. Acquire first
    # purges entries older than the max-stream TTL, so a missed release (client
    # disconnect, crash) can NEVER permanently exhaust a tenant's slots.
    _ACQUIRE_SLOT_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
local count = redis.call('ZCARD', KEYS[1])
if count < tonumber(ARGV[2]) then
    redis.call('ZADD', KEYS[1], ARGV[3], ARGV[4])
    redis.call('EXPIRE', KEYS[1], ARGV[5])
    return 1
end
return 0
"""

    async def acquire_query_slot(self, tenant_id: str, member: str, max_slots: int, ttl: int) -> bool:
        """Try to take one concurrency slot. Returns True if acquired.

        Fails OPEN (returns True) on a Redis outage — a transient cache failure
        must not block queries (G20)."""
        now = time.time()
        try:
            got = await self._r.eval(
                self._ACQUIRE_SLOT_LUA, 1, f"conc:{tenant_id}",
                now - ttl, max_slots, now, member, ttl,
            )
            return bool(int(got))
        except Exception as exc:  # noqa: BLE001
            logger.warning("acquire_query_slot failing open (Redis unavailable): %s", exc)
            return True

    async def release_query_slot(self, tenant_id: str, member: str) -> None:
        try:
            await self._r.zrem(f"conc:{tenant_id}", member)
        except Exception as exc:  # noqa: BLE001
            logger.warning("release_query_slot failed (Redis unavailable): %s", exc)

    async def active_query_slots(self, tenant_id: str) -> int:
        try:
            return int(await self._r.zcard(f"conc:{tenant_id}"))
        except Exception:  # noqa: BLE001
            return 0

    # ── Pub/sub for live events (clinic SSE, §33 P2) ─────────────────────────

    async def publish_event(self, channel: str, event: dict) -> None:
        """Publish a JSON event to a channel. Fails open (best-effort) so a Redis
        hiccup never breaks the mutating request that triggered the broadcast."""
        try:
            await self._r.publish(channel, json.dumps(event))
        except Exception as exc:  # noqa: BLE001
            logger.warning("publish_event failed (Redis unavailable): %s", exc)

    async def subscribe(self, channel: str):
        """Async generator yielding decoded event dicts published to ``channel``.
        Used by SSE endpoints; the caller closes the generator to unsubscribe."""
        pubsub = self._r.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for msg in pubsub.listen():
                if msg.get("type") == "message":
                    try:
                        yield json.loads(msg["data"])
                    except Exception:  # noqa: BLE001 — skip a malformed message
                        continue
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:  # noqa: BLE001
                pass

    # ── JWT revocation denylist (G14) ────────────────────────────────────────

    async def revoke_jti(self, jti: str, ttl: int) -> None:
        """Deny a token id until it would naturally expire (ttl seconds)."""
        if ttl <= 0:
            return
        try:
            await self._r.setex(f"revoked_jti:{jti}", ttl, "1")
        except Exception as exc:  # noqa: BLE001
            logger.warning("revoke_jti failed (Redis unavailable): %s", exc)

    async def is_jti_revoked(self, jti: str) -> bool:
        """True if the token id is on the denylist. Fails OPEN (returns False) on
        a Redis outage — a transient cache failure must not lock out valid users."""
        try:
            return bool(await self._r.exists(f"revoked_jti:{jti}"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("is_jti_revoked failing open (Redis unavailable): %s", exc)
            return False

    async def reset_demo_queries(self, tenant_id: str) -> None:
        await self._r.delete(f"demo:qpd:{tenant_id}")

    # ── Stream event replay buffer (§8.2) ────────────────────────────────────

    # Atomically RPUSH + reset TTL. Without this, a crash between the two calls
    # leaves the buffer key with no TTL, leaking it permanently in Redis.
    _PUSH_EVENT_LUA = """
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[2])
return redis.call('LLEN', KEYS[1])
"""

    # Buffer keys are namespaced by tenant_id so a query_id (returned to the
    # client in the X-Query-Id header) cannot be used to replay another tenant's
    # answer stream — a cross-tenant query_id simply resolves to an empty buffer.
    @staticmethod
    def _stream_key(tenant_id: str, query_id: str) -> str:
        return f"stream:{tenant_id}:{query_id}"

    async def push_stream_event(self, tenant_id: str, query_id: str, event: dict, ttl: int) -> None:
        key = self._stream_key(tenant_id, query_id)
        await self._r.eval(self._PUSH_EVENT_LUA, 1, key, json.dumps(event), ttl)

    async def get_stream_events(self, tenant_id: str, query_id: str, after_seq: int = 0) -> list[dict]:
        key = self._stream_key(tenant_id, query_id)
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
