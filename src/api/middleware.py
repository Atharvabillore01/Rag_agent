"""FastAPI middleware — rate limiting, request ID, CORS, audit events (§11, §21)."""

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings
from src.storage.cache import get_cache

settings = get_settings()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID on every request for tracing (§11)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiting via Redis (§21).

    Applied ONLY to /query routes — uploads, admin, and auth have different
    throughput characteristics and must not share the query QPM budget.
    Limit is per (tenant_id, minute).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if not request.url.path.startswith("/query"):
            return await call_next(request)

        # Extract tenant from JWT without full auth flow (lightweight check)
        tenant_id = self._extract_tenant_id(request)
        if not tenant_id:
            return await call_next(request)

        cache = get_cache()
        key = f"rl:qpm:{tenant_id}:{int(time.time() // 60)}"
        allowed, count = await cache.rate_limit_check(
            key, settings.rate_limit_default_qpm, window_seconds=60
        )

        if not allowed:
            return Response(
                content='{"detail":"Rate limit exceeded. Please slow down."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, settings.rate_limit_default_qpm - count)
        )
        return response

    @staticmethod
    def _extract_tenant_id(request: Request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            from jose import jwt
            payload = jwt.decode(
                auth[7:],
                settings.secret_key,
                algorithms=["HS256"],
                options={"verify_exp": False},  # just reading tenant_id, not validating
            )
            return payload.get("tenant_id")
        except Exception:
            return None


class TimingMiddleware(BaseHTTPMiddleware):
    """Add X-Response-Time header for latency monitoring (§11)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"
        return response
