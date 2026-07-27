"""Platform (super-admin) console — cross-tenant management (feature-implementation-plan §31).

Every route requires a platform admin (User.is_platform_admin) and is deliberately
NOT tenant-scoped: a platform admin manages ALL organizations. Org-scoped admin
lives in src/api/routers/admin.py.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import PasswordPolicyError, hash_password, require_platform_admin, validate_password
from src.api.deps import get_cache_dep
from src.api.limits import default_limits, invalidate_tenant_limits
from src.db.models import (AuditAction, AuditLog, Document, RateLimitConfig, Tenant,
                           TenantTier, User, UserRole)
from src.db.session import get_db
from src.storage.cache import CacheClient, get_cache

router = APIRouter(prefix="/platform", tags=["platform"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrgSummary(BaseModel):
    id: str
    name: str
    tier: str
    is_active: bool
    quota_documents: int
    quota_queries_daily: int
    user_count: int
    document_count: int
    created_at: str


class MemberOut(BaseModel):
    user_id: str
    email: str
    role: str
    is_active: bool
    is_platform_admin: bool


class OrgUsage(BaseModel):
    documents: int
    queries_today: int


class OrgDetail(BaseModel):
    id: str
    name: str
    tier: str
    is_active: bool
    quota_documents: int
    quota_queries_daily: int
    members: list[MemberOut]
    usage: OrgUsage
    created_at: str


class CreateOrgRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tier: TenantTier = TenantTier.starter
    domain: str = "generic"   # vertical: generic | legal | ca | clinic
    quota_documents: int = Field(default=100, ge=0, le=10_000_000)
    quota_queries_daily: int = Field(default=1000, ge=0, le=100_000_000)
    admin_email: EmailStr
    admin_password: str


class UpdateOrgRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    tier: TenantTier | None = None
    quota_documents: int | None = Field(default=None, ge=0, le=10_000_000)
    quota_queries_daily: int | None = Field(default=None, ge=0, le=100_000_000)
    is_active: bool | None = None


class CreateMemberRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.viewer


class UpdateMemberRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class MoveMemberRequest(BaseModel):
    target_tenant_id: str = Field(min_length=1)


class RateLimitOut(BaseModel):
    queries_per_minute: int
    queries_per_day: int
    ingestion_per_hour: int
    max_concurrent_queries: int
    is_default: bool


class RateLimitIn(BaseModel):
    queries_per_minute: int = Field(ge=1, le=100_000)
    queries_per_day: int = Field(ge=1, le=10_000_000)
    ingestion_per_hour: int = Field(ge=1, le=1_000_000)
    max_concurrent_queries: int = Field(ge=1, le=10_000)


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _get_tenant(db: AsyncSession, tenant_id: str) -> Tenant:
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail="Organization not found")
    return tenant


async def _email_taken(db: AsyncSession, email: str) -> bool:
    """True if any user (ANY tenant) already has this email. Login/registration
    resolve users by email alone, so emails must be globally unique — creating a
    cross-tenant duplicate would 500 that account's login (review HIGH)."""
    return (await db.execute(
        select(User.id).where(User.email == email).limit(1)
    )).first() is not None


_EMAIL_CONFLICT = "A user with this email already exists."


def _audit(db: AsyncSession, *, tenant_id: str, actor_id: str, action: str,
           resource_type: str, resource_id: str | None, meta: dict | None = None) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id, user_id=actor_id, action=action,
        resource_type=resource_type, resource_id=resource_id, log_metadata=meta,
    ))


# ── Organizations ──────────────────────────────────────────────────────────

@router.get("/orgs", response_model=list[OrgSummary])
async def list_orgs(
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    offset = max(0, skip)
    page = min(max(1, limit), 500)
    tenants = (await db.execute(
        select(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(page)
    )).scalars().all()
    # counts in two grouped queries (no N+1)
    user_counts = dict((await db.execute(
        select(User.tenant_id, func.count(User.id)).group_by(User.tenant_id)
    )).all())
    doc_counts = dict((await db.execute(
        select(Document.tenant_id, func.count(Document.id)).group_by(Document.tenant_id)
    )).all())
    return [
        OrgSummary(
            id=t.id, name=t.name, tier=t.tier.value, is_active=t.is_active,
            quota_documents=t.quota_documents, quota_queries_daily=t.quota_queries_daily,
            user_count=user_counts.get(t.id, 0), document_count=doc_counts.get(t.id, 0),
            created_at=t.created_at.isoformat(),
        )
        for t in tenants
    ]


@router.post("/orgs", response_model=OrgDetail, status_code=201)
async def create_org(
    body: CreateOrgRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    try:
        validate_password(body.admin_password)
    except PasswordPolicyError as exc:
        raise HTTPException(422, detail=str(exc))
    if await _email_taken(db, str(body.admin_email)):
        raise HTTPException(409, detail=_EMAIL_CONFLICT)

    from src.domains import normalize_domain
    tenant = Tenant(
        name=body.name, tier=body.tier, domain=normalize_domain(body.domain),
        quota_documents=body.quota_documents, quota_queries_daily=body.quota_queries_daily,
    )
    db.add(tenant)
    await db.flush()

    admin = User(
        tenant_id=tenant.id, email=str(body.admin_email),
        hashed_password=hash_password(body.admin_password),
        role=UserRole.org_admin, is_active=True,
    )
    db.add(admin)
    try:
        await db.flush()  # surface any uniqueness violation + populate admin.id for the audit row
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, detail=_EMAIL_CONFLICT)
    _audit(db, tenant_id=tenant.id, actor_id=current_user.id,
           action=AuditAction.tenant_create.value, resource_type="tenant", resource_id=tenant.id,
           meta={"name": tenant.name, "tier": tenant.tier.value})
    _audit(db, tenant_id=tenant.id, actor_id=current_user.id,
           action=AuditAction.user_create.value, resource_type="user", resource_id=admin.id,
           meta={"email": admin.email, "role": admin.role.value})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, detail=_EMAIL_CONFLICT)
    await db.refresh(tenant)
    logger.info("platform: org created", extra={"tenant_id": tenant.id, "by": current_user.id})
    return await _org_detail(db, tenant, get_cache())


async def _org_detail(db: AsyncSession, tenant: Tenant, cache: CacheClient) -> OrgDetail:
    members = (await db.execute(
        select(User).where(User.tenant_id == tenant.id).order_by(User.created_at)
    )).scalars().all()
    doc_count = (await db.execute(
        select(func.count(Document.id)).where(Document.tenant_id == tenant.id)
    )).scalar() or 0
    queries_today = await cache.get_rate_limit_count(f"qpd:{tenant.id}")
    demo_today = await cache.get_rate_limit_count(f"demo:qpd:{tenant.id}")
    return OrgDetail(
        id=tenant.id, name=tenant.name, tier=tenant.tier.value, is_active=tenant.is_active,
        quota_documents=tenant.quota_documents, quota_queries_daily=tenant.quota_queries_daily,
        members=[
            MemberOut(user_id=u.id, email=u.email, role=u.role.value,
                      is_active=u.is_active, is_platform_admin=u.is_platform_admin)
            for u in members
        ],
        usage=OrgUsage(documents=doc_count, queries_today=queries_today + demo_today),
        created_at=tenant.created_at.isoformat(),
    )


@router.get("/orgs/{tenant_id}", response_model=OrgDetail)
async def get_org(
    tenant_id: str,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
    cache: CacheClient = Depends(get_cache_dep),
):
    tenant = await _get_tenant(db, tenant_id)
    return await _org_detail(db, tenant, cache)


@router.patch("/orgs/{tenant_id}", response_model=OrgDetail)
async def update_org(
    tenant_id: str,
    body: UpdateOrgRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
    cache: CacheClient = Depends(get_cache_dep),
):
    tenant = await _get_tenant(db, tenant_id)
    changed = {}
    if body.name is not None:
        tenant.name = body.name; changed["name"] = body.name
    if body.tier is not None:
        tenant.tier = body.tier; changed["tier"] = body.tier.value
    if body.quota_documents is not None:
        tenant.quota_documents = body.quota_documents; changed["quota_documents"] = body.quota_documents
    if body.quota_queries_daily is not None:
        tenant.quota_queries_daily = body.quota_queries_daily; changed["quota_queries_daily"] = body.quota_queries_daily
    if body.is_active is not None:
        tenant.is_active = body.is_active; changed["is_active"] = body.is_active
    _audit(db, tenant_id=tenant.id, actor_id=current_user.id,
           action=AuditAction.admin_action.value, resource_type="tenant", resource_id=tenant.id,
           meta={"update": changed})
    await db.commit()
    await db.refresh(tenant)
    return await _org_detail(db, tenant, cache)


# ── Members (cross-tenant) ──────────────────────────────────────────────────

@router.post("/orgs/{tenant_id}/members", response_model=MemberOut, status_code=201)
async def add_member(
    tenant_id: str,
    body: CreateMemberRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_tenant(db, tenant_id)
    try:
        validate_password(body.password)
    except PasswordPolicyError as exc:
        raise HTTPException(422, detail=str(exc))
    # Global (not per-tenant) email check — emails must be unique across all orgs
    # or the account's login 500s (review HIGH).
    if await _email_taken(db, str(body.email)):
        raise HTTPException(409, detail=_EMAIL_CONFLICT)
    user = User(
        tenant_id=tenant_id, email=str(body.email),
        hashed_password=hash_password(body.password), role=body.role, is_active=True,
    )
    db.add(user)
    try:
        await db.flush()  # populate user.id for the audit row + catch a concurrent duplicate
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, detail=_EMAIL_CONFLICT)
    _audit(db, tenant_id=tenant_id, actor_id=current_user.id,
           action=AuditAction.user_create.value, resource_type="user", resource_id=user.id,
           meta={"email": str(body.email), "role": body.role.value})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, detail=_EMAIL_CONFLICT)
    await db.refresh(user)
    return MemberOut(user_id=user.id, email=user.email, role=user.role.value,
                     is_active=user.is_active, is_platform_admin=user.is_platform_admin)


@router.patch("/orgs/{tenant_id}/members/{user_id}", response_model=MemberOut)
async def update_member(
    tenant_id: str,
    user_id: str,
    body: UpdateMemberRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, detail="Member not found in this organization")
    changed = {}
    if body.role is not None:
        user.role = body.role; changed["role"] = body.role.value
    if body.is_active is not None:
        user.is_active = body.is_active; changed["is_active"] = body.is_active
    _audit(db, tenant_id=tenant_id, actor_id=current_user.id,
           action=AuditAction.role_change.value, resource_type="user", resource_id=user.id,
           meta={"update": changed})
    await db.commit()
    await db.refresh(user)
    return MemberOut(user_id=user.id, email=user.email, role=user.role.value,
                     is_active=user.is_active, is_platform_admin=user.is_platform_admin)


@router.post("/orgs/{tenant_id}/members/{user_id}/move", response_model=MemberOut)
async def move_member(
    tenant_id: str,
    user_id: str,
    body: MoveMemberRequest,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    """Move a user from their current org to another (e.g. onto a different-tier org).

    Only the user record moves; documents they uploaded stay with the original org
    (owned by its tenant_id). Their collection tags are cleared since they refer to
    the old org's collections.
    """
    if body.target_tenant_id == tenant_id:
        raise HTTPException(400, detail="User is already in this organization.")
    user = (await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, detail="Member not found in this organization")
    await _get_tenant(db, body.target_tenant_id)  # 404 if the target org doesn't exist

    user.tenant_id = body.target_tenant_id
    user.collection_tags = None  # old-org collection tags don't apply in the new org
    _audit(db, tenant_id=body.target_tenant_id, actor_id=current_user.id,
           action=AuditAction.admin_action.value, resource_type="user", resource_id=user.id,
           meta={"moved_from": tenant_id, "moved_to": body.target_tenant_id})
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, detail=_EMAIL_CONFLICT)
    await db.refresh(user)
    return MemberOut(user_id=user.id, email=user.email, role=user.role.value,
                     is_active=user.is_active, is_platform_admin=user.is_platform_admin)


# ── Per-org rate limits ─────────────────────────────────────────────────────

@router.get("/orgs/{tenant_id}/rate-limit", response_model=RateLimitOut)
async def get_org_rate_limit(
    tenant_id: str,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    await _get_tenant(db, tenant_id)
    row = (await db.execute(
        select(RateLimitConfig).where(RateLimitConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if row is None:
        d = default_limits()
        return RateLimitOut(queries_per_minute=d.qpm, queries_per_day=d.qpd,
                            ingestion_per_hour=d.ingestion_per_hour,
                            max_concurrent_queries=d.max_concurrent, is_default=True)
    return RateLimitOut(queries_per_minute=row.queries_per_minute, queries_per_day=row.queries_per_day,
                        ingestion_per_hour=row.ingestion_per_hour,
                        max_concurrent_queries=row.max_concurrent_queries, is_default=False)


@router.put("/orgs/{tenant_id}/rate-limit", response_model=RateLimitOut)
async def set_org_rate_limit(
    tenant_id: str,
    body: RateLimitIn,
    current_user: User = Depends(require_platform_admin),
    db: AsyncSession = Depends(get_db),
):
    tenant = await _get_tenant(db, tenant_id)
    row = (await db.execute(
        select(RateLimitConfig).where(RateLimitConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()
    if row is None:
        row = RateLimitConfig(tenant_id=tenant_id, tier=tenant.tier.value)
        db.add(row)
    row.tier = tenant.tier.value
    row.queries_per_minute = body.queries_per_minute
    row.queries_per_day = body.queries_per_day
    row.ingestion_per_hour = body.ingestion_per_hour
    row.max_concurrent_queries = body.max_concurrent_queries
    _audit(db, tenant_id=tenant_id, actor_id=current_user.id,
           action=AuditAction.admin_action.value, resource_type="rate_limit", resource_id=tenant_id,
           meta=body.model_dump())
    await db.commit()
    await invalidate_tenant_limits(tenant_id)
    return RateLimitOut(queries_per_minute=row.queries_per_minute, queries_per_day=row.queries_per_day,
                        ingestion_per_hour=row.ingestion_per_hour,
                        max_concurrent_queries=row.max_concurrent_queries, is_default=False)
