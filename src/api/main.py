"""FastAPI application entry point — lifespan, middleware, router registration (§15)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.middleware import RateLimitMiddleware, RequestIDMiddleware, TimingMiddleware
from src.api.routers import admin, auth_router, contentions, crossexam, documents, drafting, folders, lod, pii, playbook, query, redline, review, skills, transcribe, translation
from src.config import get_settings
from src.logging_config import configure_logging

# Configure file + console logging before anything else runs
configure_logging("api")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify storage connectivity. Shutdown: close connections."""
    # Verify MinIO bucket
    from src.storage.object import get_object_store
    get_object_store().ensure_bucket()

    # Verify Redis connection
    from src.storage.cache import get_cache
    await get_cache().ping()

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


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name}


@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.app_name}. See /docs for API reference."}
