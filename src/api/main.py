"""FastAPI application entry point — lifespan, middleware, router registration (§15)."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware import RateLimitMiddleware, RequestIDMiddleware, TimingMiddleware
from src.api.routers import admin, auth_router, clinic, contentions, crossexam, documents, drafting, folders, lod, pii, platform, playbook, query, redline, review, skills, transcribe, translation
from src.config import get_settings
from src.logging_config import configure_logging

# Configure file + console logging before anything else runs
configure_logging("api")

settings = get_settings()


_startup_log = logging.getLogger("duckvault.startup")


async def _await_dependency(check, *, name: str, hint: str, attempts: int = 5, delay: float = 2.0) -> None:
    """Run a startup connectivity check with brief retries (dependencies may still
    be booting), then fail with a clear, actionable error instead of a raw
    driver traceback + silent exit."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = check()
            if asyncio.iscoroutine(result):
                await result
            return
        except Exception as exc:  # noqa: BLE001 — surface a friendly message below
            last_exc = exc
            _startup_log.warning("startup: %s not ready (%d/%d): %s", name, attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(delay)
    raise RuntimeError(f"{name} unreachable on startup. {hint} (last error: {last_exc})") from last_exc


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify storage connectivity (resilient). Shutdown: close connections."""
    from src.storage.cache import get_cache
    from src.storage.object import get_object_store

    await _await_dependency(
        lambda: get_object_store().ensure_bucket(),
        name=f"Object storage ({settings.s3_endpoint_url})",
        hint="Is MinIO running? Start it with `docker compose up -d minio`.",
    )
    await _await_dependency(
        lambda: get_cache().ping(),
        name=f"Redis ({settings.redis_url})",
        hint="Is Redis running? Start it with `docker compose up -d redis`.",
    )

    yield

    # Cleanup: dispose of async engine
    from src.db.session import engine
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="DuckVault — multi-tenant agentic RAG for professional document intelligence (local-first, provider-agnostic)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# ── Middleware (order matters — outermost wraps all) ──────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TimingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIDMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router.router)
app.include_router(documents.router)
app.include_router(query.router)
app.include_router(admin.router)
app.include_router(review.router)
app.include_router(redline.router)
app.include_router(translation.router)
app.include_router(lod.router)
app.include_router(drafting.router)
app.include_router(folders.router)
app.include_router(transcribe.router)
app.include_router(skills.router)
app.include_router(contentions.router)
app.include_router(pii.router)
app.include_router(crossexam.router)
app.include_router(playbook.router)
app.include_router(platform.router)
app.include_router(clinic.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.app_name}. See /docs for API reference."}
