"""FastAPI middleware — rate limiting, request ID, CORS, audit events (§11, §21)."""

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import get_settings
from src.storage.cache import get_cache

settings = get_settings()

_timing_logger = logging.getLogger("api.timing")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID on every request for tracing (§11)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# POST requests under these prefixes are LLM-cost operations and share the
# per-tenant per-minute (QPM) budget. GET/DELETE (reads, exports, deletes) are
# cheap and NOT metered. Uploads are metered separately (per-hour ingestion).
_METERED_POST_PREFIXES = (
    "/query", "/review", "/redline", "/translation", "/lod", "/drafting", "/contentions", "/pii",
)
_UPLOAD_PREFIX = "/documents/upload"


def _rate_limited(detail: str, retry_after: int) -> Response:
    return Response(
        content=f'{{"detail":"{detail}"}}',
        status_code=429,
        media_type="application/json",
        headers={"Retry-After": str(retry_after)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-tenant rate limiting via Redis (§21, §27).

    Two independent fixed-window budgets, both keyed per tenant and sourced from
    the tenant's ``RateLimitConfig`` (falling back to settings defaults):

    * QPM — POST requests to the metered LLM endpoints (query + feature routers).
    * Ingestion/hour — ``POST /documents/upload``.

    Reads/exports/deletes are never throttled. Fails OPEN on a Redis outage.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        method = request.method
        path = request.url.path

        # Fast path: only POSTs to metered routes are candidates.
        is_upload = method == "POST" and path.startswith(_UPLOAD_PREFIX)
        is_metered = method == "POST" and any(path.startswith(p) for p in _METERED_POST_PREFIXES)
        if not (is_upload or is_metered):
            return await call_next(request)

        tenant_id = self._extract_tenant_id(request)
        if not tenant_id:
            # No valid token -> let the endpoint's auth dependency reject it (401),
            # and never attribute usage to a tenant we can't identify.
            return await call_next(request)

        from src.api.limits import resolve_tenant_limits
        cache = get_cache()
        limits = await resolve_tenant_limits(tenant_id)

        if is_upload:
            key = f"ing:hph:{tenant_id}:{int(time.time() // 3600)}"
            count = await cache.incr_window(key, ttl=3600)
            if count > limits.ingestion_per_hour:
                return _rate_limited(
                    f"Hourly upload limit reached ({limits.ingestion_per_hour}). Please try again later.",
                    3600,
                )
            response = await call_next(request)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limits.ingestion_per_hour - count))
            return response

        # metered LLM POST -> QPM budget
        key = f"rl:qpm:{tenant_id}:{int(time.time() // 60)}"
        allowed, count = await cache.rate_limit_check(key, limits.qpm, window_seconds=60)
        if not allowed:
            return _rate_limited("Rate limit exceeded. Please slow down.", 60)
        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limits.qpm - count))
        return response

    @staticmethod
    def _extract_tenant_id(request: Request) -> str | None:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        try:
            # Verify signature, expiry, issuer AND audience (tokens now carry
            # iss/aud — decoding without them would raise). An expired/invalid
            # token must not be trusted to attribute rate-limit usage to a tenant
            # (it could poison another tenant's bucket); on failure -> None.
            from src.api.auth import decode_token
            payload = decode_token(auth[7:])
            return payload.get("tenant_id")
        except Exception:
            return None


class TimingMiddleware(BaseHTTPMiddleware):
    """Add X-Response-Time header and write a structured runtime log line (§11).

    Every request is logged to the ``api.timing`` logger at INFO level:
        METHOD /path  status=<code>  runtime=<N>ms  request_id=<id>

    Upload requests (POST /documents/upload) are additionally logged at a
    higher-visibility level so they are easy to grep in logs/api.log:
        grep "UPLOAD" logs/api.log
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Always set the response header
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

        # Build a structured log line
        method = request.method
        path = request.url.path
        status = response.status_code
        request_id = getattr(request.state, "request_id", "-")
        content_length = request.headers.get("content-length", "-")

        log_msg = (
            f"{method} {path}  status={status}  runtime={elapsed_ms:.1f}ms"
            f"  request_id={request_id}  content_length={content_length}"
        )

        is_upload = method == "POST" and path.startswith("/documents/upload")

        if is_upload:
            # Prominent line so uploads are instantly greppable
            _timing_logger.info("UPLOAD %s", log_msg)
            if status >= 400:
                _timing_logger.warning("UPLOAD_FAILED %s", log_msg)
        else:
            _timing_logger.debug(log_msg)

        return response

