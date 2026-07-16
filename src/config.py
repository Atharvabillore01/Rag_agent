from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "DuckVault"
    debug: bool = False
    secret_key: str = _INSECURE_SECRET
    access_token_expire_minutes: int = 60 * 24  # 24 h
    # JWTs are signed with secret_key (HS256). Anyone who knows it can forge a
    # token for any user/tenant/role, so the placeholder default must never be
    # used to actually run the app — see the validator below.
    cors_allow_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Registration (G5) ──────────────────────────────────────────────────────
    # Self-serve registration is OFF by default: it provisions a brand-new tenant
    # with an org_admin for the caller, so leaving it open lets anyone mint an
    # admin account. Enable explicitly for dev/self-serve, or restrict to an
    # email-domain allowlist.
    allow_open_registration: bool = False
    registration_allowed_domains: list[str] = []
    # G6: per-IP throttle on /auth/login and /auth/register (attempts per minute).
    auth_rate_limit_per_minute: int = 10
    # G14: JWT hardening — issuer/audience claims are set and verified.
    jwt_issuer: str = "duckvault"
    jwt_audience: str = "duckvault-api"
    # G15: password policy (bcrypt caps at 72 bytes; enforced in validate_password).
    min_password_length: int = 8
    # G11: at-rest field encryption key for sensitive content columns. If empty,
    # a key is derived from SECRET_KEY (so it works out of the box); set a
    # dedicated key to rotate it independently of SECRET_KEY.
    field_encryption_key: str = ""

    @model_validator(mode="after")
    def _reject_insecure_secret(self) -> "Settings":
        # Fail fast rather than silently signing tokens with a public default.
        if self.secret_key == _INSECURE_SECRET:
            raise ValueError(
                "SECRET_KEY is set to the insecure default. Generate a strong "
                "value (e.g. `python -c \"import secrets; print(secrets.token_hex(32))\"`) "
                "and set SECRET_KEY in your .env before starting."
            )
        return self

    @model_validator(mode="after")
    def _reject_default_infra_creds(self) -> "Settings":
        # In production (debug=False) refuse to boot on default/insecure
        # infrastructure credentials. Local dev (debug=True) is unaffected.
        if self.debug:
            return self
        problems: list[str] = []
        if self.s3_access_key == "minioadmin" or self.s3_secret_key == "minioadmin":
            problems.append("S3/MinIO uses the default 'minioadmin' credentials")
        if "rag:rag@" in self.database_url:
            problems.append("DATABASE_URL uses the default 'rag:rag' credentials")
        if not self.qdrant_api_key:
            problems.append("QDRANT_API_KEY is empty")
        if problems:
            raise ValueError(
                "Insecure default infrastructure credentials detected with DEBUG=false. "
                "Set real credentials (or DEBUG=true for local dev): " + "; ".join(problems)
            )
        return self

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://rag:rag@localhost:5432/ragdb"
    db_pool_size: int = 20          # raised from 10 — SSE streaming holds sessions open
    db_max_overflow: int = 30       # raised from 20 — up to 50 concurrent streaming sessions
    db_pool_recycle: int = 3600     # recycle idle connections after 1 h

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Celery ────────────────────────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_min_concurrency: int = 2   # idle floor — always-ready workers
    celery_max_concurrency: int = 20  # peak ceiling — scales up under load

    # ── Qdrant ────────────────────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""

    # ── MinIO / S3 ────────────────────────────────────────────────────────────
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket_name: str = "rag-documents"
    s3_region: str = "us-east-1"

    # ── Ingestion ─────────────────────────────────────────────────────────────
    max_upload_size_bytes: int = 100 * 1024 * 1024   # 100 MB
    demo_max_upload_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    ingestion_fast_queue: str = "ingestion.fast"
    ingestion_demo_queue: str = "ingestion.demo"

    # ── Agent ─────────────────────────────────────────────────────────────────
    agent_max_retrieval_rounds: int = 3
    demo_max_retrieval_rounds: int = 2
    agent_retrieval_top_k: int = 20       # candidates before rerank
    agent_rerank_top_n: int = 5           # after rerank
    agent_doc_metadata_limit: int = 200   # max documents surfaced to planner
    query_cache_ttl_seconds: int = 300    # 5 min query cache in Redis
    stream_buffer_ttl_seconds: int = 900  # 15 min replay buffer

    # ── Rate limiting ─────────────────────────────────────────────────────────
    rate_limit_default_qpm: int = 20       # queries per minute
    rate_limit_default_qpd: int = 1000     # queries per day
    rate_limit_demo_qpd: int = 30

    # ── Demo quotas ───────────────────────────────────────────────────────────
    demo_max_documents: int = 5
    demo_inactivity_days: int = 14

    # ── OTEL ─────────────────────────────────────────────────────────────────
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "rag-platform"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
