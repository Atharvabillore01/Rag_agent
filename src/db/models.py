"""SQLAlchemy ORM models — canonical schema from spec §9.1."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.db.crypto import EncryptedText  # G11: at-rest encryption for content columns


# ── Base ─────────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Enums ─────────────────────────────────────────────────────────────────────

class TenantTier(str, enum.Enum):
    demo = "demo"
    starter = "starter"
    pro = "pro"
    enterprise = "enterprise"


class UserRole(str, enum.Enum):
    org_admin = "org_admin"
    editor = "editor"
    viewer = "viewer"
    demo = "demo"


class DocumentStatus(str, enum.Enum):
    # happy path
    uploaded = "uploaded"
    scanning = "scanning"
    parsing = "parsing"
    cleaning = "cleaning"
    chunking = "chunking"
    embedding = "embedding"
    indexing = "indexing"
    ready = "ready"
    ready_with_warnings = "ready_with_warnings"
    # failure states
    failed_retryable = "failed_retryable"
    failed_terminal = "failed_terminal"
    rejected_security = "rejected_security"
    quota_exceeded = "quota_exceeded"


class IngestionStage(str, enum.Enum):
    upload = "upload"
    scanning = "scanning"
    parsing = "parsing"
    cleaning = "cleaning"
    chunking = "chunking"
    embedding = "embedding"
    indexing = "indexing"


class ChunkType(str, enum.Enum):
    prose = "prose"
    table = "table"
    figure_description = "figure_description"
    slide = "slide"


class AuditAction(str, enum.Enum):
    document_upload = "document_upload"
    document_delete = "document_delete"
    document_query = "document_query"
    user_login = "user_login"
    user_create = "user_create"
    user_delete = "user_delete"
    role_change = "role_change"
    tenant_create = "tenant_create"
    tenant_delete = "tenant_delete"
    admin_action = "admin_action"


# ── Tenants ───────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[TenantTier] = mapped_column(
        Enum(TenantTier), nullable=False, default=TenantTier.starter
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Vertical domain pack this tenant runs — drives prompts, skills library,
    # citation sources, and extraction schemas (multi-domain plan §3). Kept a
    # plain string (not an Enum) on purpose: onboarding a new vertical should be
    # a config change, not a schema migration. "generic" is the domain-agnostic
    # default that behaves exactly like the platform did before domain packs.
    domain: Mapped[str] = mapped_column(
        String(50), nullable=False, default="generic", server_default="generic"
    )

    # Per-tenant provider overrides (§2.3)
    llm_provider_override: Mapped[str | None] = mapped_column(String(50))
    llm_model_override: Mapped[str | None] = mapped_column(String(100))
    embed_provider_override: Mapped[str | None] = mapped_column(String(50))

    # Quota caps
    quota_documents: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    quota_queries_daily: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="tenant")
    demo_quota: Mapped["DemoQuota | None"] = relationship("DemoQuota", back_populates="tenant", uselist=False)
    rate_limit_config: Mapped["RateLimitConfig | None"] = relationship(
        "RateLimitConfig", back_populates="tenant", uselist=False
    )
    vector_indexes: Mapped[list["TenantVectorIndex"]] = relationship(
        "TenantVectorIndex", back_populates="tenant"
    )


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255))  # null if SSO-only
    # MFA (G10): TOTP secret encrypted at rest; enabled only after a code is verified.
    mfa_secret: Mapped[str | None] = mapped_column(EncryptedText)
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False, default=UserRole.viewer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    collection_tags: Mapped[list | None] = mapped_column(JSON)  # accessible collections

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="users")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="uploaded_by_user")


# ── Documents ─────────────────────────────────────────────────────────────────

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)  # pdf | docx | pptx | image
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    # SHA-256 of raw bytes — used for duplicate detection (§16.3)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), nullable=False, default=DocumentStatus.uploaded
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    ingestion_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # RBAC scoping
    collection_tags: Mapped[list | None] = mapped_column(JSON)

    # Folder / matter organization (feature-implementation-plan §23). SET NULL on
    # folder delete so documents are unfiled, never cascaded away.
    folder_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
    )

    page_count: Mapped[int | None] = mapped_column(Integer)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "content_hash", name="uq_document_tenant_hash"),
        # Without these indexes every document list/status query is a full table scan.
        # At 10k docs across 10 tenants: ~1000 rows scanned per request without them.
        Index("ix_documents_tenant_id", "tenant_id"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_tenant_status", "tenant_id", "status"),
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="documents")
    uploaded_by_user: Mapped[User | None] = relationship("User", back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        "IngestionJob", back_populates="document", cascade="all, delete-orphan"
    )


# ── Ingestion jobs ────────────────────────────────────────────────────────────

class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)

    stage: Mapped[IngestionStage] = mapped_column(Enum(IngestionStage), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    input_artifact_uri: Mapped[str | None] = mapped_column(String(1024))
    output_artifact_uri: Mapped[str | None] = mapped_column(String(1024))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(Text)

    document: Mapped[Document] = relationship("Document", back_populates="ingestion_jobs")


# ── Chunks ────────────────────────────────────────────────────────────────────

class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(EncryptedText, nullable=False)  # G11: encrypted at rest
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Hierarchical retrieval (§3.3)
    parent_chunk_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("chunks.id", ondelete="SET NULL")
    )

    page_number: Mapped[int | None] = mapped_column(Integer)
    section_heading: Mapped[str | None] = mapped_column(String(512))

    # Embedding provenance — required for migration safety (§9.3)
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    embedding_version: Mapped[str | None] = mapped_column(String(50))

    chunk_type: Mapped[ChunkType] = mapped_column(
        Enum(ChunkType), nullable=False, default=ChunkType.prose
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunks_tenant_id", "tenant_id"),
    )

    document: Mapped[Document] = relationship("Document", back_populates="chunks")
    children: Mapped[list["Chunk"]] = relationship(
        "Chunk",
        foreign_keys=[parent_chunk_id],
        back_populates="parent",
    )
    parent: Mapped["Chunk | None"] = relationship(
        "Chunk",
        foreign_keys=[parent_chunk_id],
        back_populates="children",
        remote_side="Chunk.id",
    )


# ── Audit log ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36))  # null for system actions

    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100))
    resource_id: Mapped[str | None] = mapped_column(String(36))

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # "metadata" is reserved by SQLAlchemy's DeclarativeBase — use log_metadata
    log_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)

    __table_args__ = (
        Index("ix_audit_log_tenant_id", "tenant_id"),
        Index("ix_audit_log_timestamp", "timestamp"),
    )


# ── Demo quotas ───────────────────────────────────────────────────────────────

class DemoQuota(Base):
    __tablename__ = "demo_quotas"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    documents_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queries_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="demo_quota")


# ── Rate limit config ─────────────────────────────────────────────────────────

class RateLimitConfig(Base):
    __tablename__ = "rate_limit_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    tier: Mapped[str] = mapped_column(String(50), nullable=False)

    queries_per_minute: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    queries_per_day: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    ingestion_per_hour: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    max_concurrent_queries: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="rate_limit_config")


# ── Vector index metadata ─────────────────────────────────────────────────────

class TenantVectorIndex(Base):
    """Tracks per-tenant Qdrant collection metadata for migration safety (§9.3)."""

    __tablename__ = "tenant_vector_indexes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="qdrant")
    physical_name: Mapped[str] = mapped_column(String(255), nullable=False)  # qdrant collection name
    vector_model: Mapped[str] = mapped_column(String(100), nullable=False)
    vector_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1")
    shard_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    cutover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="vector_indexes")


# ── Parallel Review (feature-implementation-plan §3) ──────────────────────────

class ParallelReview(Base):
    """A saved "N documents × M questions → answers table" run.

    Structured extraction across a fixed, user-selected set of documents,
    answered ONLY from those documents (no external retrieval). Questions and
    per-document answers are stored as JSON so a review is fully re-viewable and
    columns can be appended without a schema change.
    """

    __tablename__ = "parallel_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Documents included in this review (list of document ids).
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    # Columns: list of {key, header, question}.
    questions: Mapped[list] = mapped_column(JSON, nullable=False)
    # Answers: {doc_id: {filename, answers: {key: answer}, truncated: bool, error: str|null}}.
    # Null until the run completes.
    results: Mapped[dict | None] = mapped_column(JSON)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_parallel_reviews_tenant_id", "tenant_id"),
        Index("ix_parallel_reviews_tenant_created", "tenant_id", "created_at"),
    )


# ── Redline / document diff (feature-implementation-plan §8) ──────────────────

class Redline(Base):
    """A saved Change -> Consequence comparison of two documents.

    The factual diff is computed deterministically (difflib); the LLM only
    explains each change's consequence. Results are stored as JSON so the
    comparison is fully re-viewable.
    """

    __tablename__ = "redlines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revised_document_id: Mapped[str] = mapped_column(String(36), nullable=False)

    # list of {change_type, before, after, change, consequence}
    results: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_redlines_tenant_id", "tenant_id"),
        Index("ix_redlines_tenant_created", "tenant_id", "created_at"),
    )


# ── Translation (feature-implementation-plan §9) ──────────────────────────────

class Translation(Base):
    """A saved translation of a document into a target language."""

    __tablename__ = "translations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(512))
    target_language: Mapped[str] = mapped_column(String(80), nullable=False)

    result: Mapped[str | None] = mapped_column(EncryptedText)   # translated text (G11: encrypted at rest)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_translations_tenant_id", "tenant_id"),
        Index("ix_translations_tenant_created", "tenant_id", "created_at"),
    )


# ── List of Dates / chronology (feature-implementation-plan §11) ──────────────

class ListOfDates(Base):
    """A saved chronological List of Dates built from one or more documents.

    Dates are found deterministically in the source text; the LLM only
    summarizes each event and normalizes the date. Entries are stored as JSON.
    """

    __tablename__ = "list_of_dates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    # list of {date, iso_date, event, document_id, filename, page_number, snippet}
    results: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_list_of_dates_tenant_id", "tenant_id"),
        Index("ix_list_of_dates_tenant_created", "tenant_id", "created_at"),
    )


# ── Drafting assistant (feature-implementation-plan §13) ──────────────────────

class Draft(Base):
    """A generated document draft, grounded in and cited to source documents."""

    __tablename__ = "drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)

    content: Mapped[str | None] = mapped_column(EncryptedText)   # markdown draft (G11: encrypted at rest)
    # list of {number, document_id, filename}
    citations: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_drafts_tenant_id", "tenant_id"),
        Index("ix_drafts_tenant_created", "tenant_id", "created_at"),
    )


# ── Contentions Comparison / pleadings analysis (feature-implementation-plan §26) ─

class ContentionAnalysis(Base):
    """A saved comparison of rival contentions across a set of pleadings.

    The disputed issues are derived by the model itself (not user-supplied like
    Parallel Review); each pleading's stance on each issue is then classified and
    an overall dispute summary is written. `issues` and `results` are stored as
    JSON (structured, re-viewable); `summary` is EncryptedText because it is a
    narrative analysis of client documents (G11, like Draft/Translation).
    """

    __tablename__ = "contention_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    # Derived issues: list of {key, title, summary}.
    issues: Mapped[list | None] = mapped_column(JSON)
    # Per-document positions: list of
    #   {document_id, filename, stances: {issue_key: {stance, text}}, error: str|null}.
    results: Mapped[list | None] = mapped_column(JSON)
    # Narrative dispute summary (G11: encrypted at rest).
    summary: Mapped[str | None] = mapped_column(EncryptedText)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_contention_analyses_tenant_id", "tenant_id"),
        Index("ix_contention_analyses_tenant_created", "tenant_id", "created_at"),
    )


# ── Sensitive-data scan / PII (feature-implementation-plan §28) ───────────────

class SensitiveScan(Base):
    """A saved PII / sensitive-data scan over a set of documents.

    Privacy by design: `results` stores only *masked* findings
    ({type, masked, snippet, page}) and never the raw identifier — so this record
    is not itself a PII store. Redaction re-derives from the live document.
    """

    __tablename__ = "sensitive_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    # list of {document_id, filename, findings: [{type, masked, snippet, page}], counts}
    results: Mapped[list | None] = mapped_column(JSON)
    # {counts: {type: n}, total: n}
    summary: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_sensitive_scans_tenant_id", "tenant_id"),
        Index("ix_sensitive_scans_tenant_created", "tenant_id", "created_at"),
    )


# ── Cross-Examination generator (feature-implementation-plan §29) ─────────────

class CrossExam(Base):
    """A saved cross-examination plan generated from source documents.

    Questions grouped by theme, each with objective/basis/type. Stored as JSON
    (analytical structure, re-viewable), like Parallel Review / Contentions.
    """

    __tablename__ = "cross_exams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    instruction: Mapped[str | None] = mapped_column(Text)  # optional case theory
    # list of {topic, questions: [{question, objective, basis, type}]}
    results: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_cross_exams_tenant_id", "tenant_id"),
        Index("ix_cross_exams_tenant_created", "tenant_id", "created_at"),
    )


# ── Contract Playbook Review (feature-implementation-plan §30) ────────────────

class PlaybookReview(Base):
    """A saved contract-vs-playbook clause deviation review.

    Per clause type: status (meets/deviates/missing) + risk + the contract's
    position + a recommendation. Stored as JSON (analytical structure).
    """

    __tablename__ = "playbook_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    # the effective playbook used: list of {clause_type, standard}
    playbook: Mapped[list | None] = mapped_column(JSON)
    # list of {clause_type, standard, status, risk, document_position, recommendation}
    results: Mapped[list | None] = mapped_column(JSON)
    # {by_status: {...}, by_risk: {...}}
    summary: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_playbook_reviews_tenant_id", "tenant_id"),
        Index("ix_playbook_reviews_tenant_created", "tenant_id", "created_at"),
    )


# ── Folders / matters (feature-implementation-plan §23) ───────────────────────

class Folder(Base):
    """A folder ("matter") for organizing documents within a tenant."""

    __tablename__ = "folders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_folders_tenant_id", "tenant_id"),
    )
