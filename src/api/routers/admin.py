"""Admin endpoints — user management, tenant config, audit log (§6, §11)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_admin
from src.db.models import AuditLog, RateLimitConfig, Tenant, User, UserRole
from src.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


class UserCreateRequest(BaseModel):
    email: EmailStr
    role: UserRole
    password: str


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: str
    is_active: bool


class AuditLogItem(BaseModel):
    id: str
    action: str
    resource_type: str | None
    resource_id: str | None
    user_id: str | None
    timestamp: str
    metadata: dict | None


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreateRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from src.api.auth import hash_password, validate_password

    # G15: apply the password policy to admin-created users too.
    try:
        validate_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    existing = await db.execute(
        select(User).where(User.email == body.email, User.tenant_id == current_user.tenant_id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already exists in this tenant")

    user = User(
        tenant_id=current_user.tenant_id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    db.add(user)

    log = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="user_create",
        resource_type="user",
        log_metadata={"email": body.email, "role": body.role.value},
    )
    db.add(log)
    await db.commit()

    return UserResponse(
        user_id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id)
    )
    users = result.scalars().all()
    return [
        UserResponse(
            user_id=u.id,
            email=u.email,
            role=u.role.value,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.patch("/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: UserRole,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.id == user_id, User.tenant_id == current_user.tenant_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user.role
    user.role = role

    log = AuditLog(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="role_change",
        resource_type="user",
        resource_id=user_id,
        log_metadata={"old_role": old_role.value, "new_role": role.value},
    )
    db.add(log)
    await db.commit()
    return {"user_id": user_id, "role": role.value}


@router.get("/audit-log", response_model=list[AuditLogItem])
async def get_audit_log(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == current_user.tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        AuditLogItem(
            id=log.id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            user_id=log.user_id,
            timestamp=log.timestamp.isoformat(),
            metadata=log.log_metadata,
        )
        for log in logs
    ]


@router.get("/observability")
async def get_observability(
    action: str | None = None,
    user_id: str | None = None,
    skip: int = 0,
    limit: int = 200,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enriched activity feed with per-user email resolution and 24h stats."""
    tenant_id = current_user.tenant_id
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    # Resolve user_id → email for this tenant
    user_rows = await db.execute(
        select(User.id, User.email, User.role, User.last_login_at)
        .where(User.tenant_id == tenant_id)
    )
    user_map = {r[0]: {"email": r[1], "role": r[2].value, "last_login_at": r[3].isoformat() if r[3] else None}
                for r in user_rows.fetchall()}

    # 24h stats
    queries_today = (await db.execute(
        select(func.count()).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "document_query",
            AuditLog.timestamp >= day_ago,
        )
    )).scalar() or 0

    logins_today = (await db.execute(
        select(func.count()).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "user_login",
            AuditLog.timestamp >= day_ago,
        )
    )).scalar() or 0

    active_users_today = (await db.execute(
        select(func.count(AuditLog.user_id.distinct())).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.timestamp >= day_ago,
            AuditLog.user_id.isnot(None),
        )
    )).scalar() or 0

    total_queries = (await db.execute(
        select(func.count()).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.action == "document_query",
        )
    )).scalar() or 0

    # Filtered log
    q = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.timestamp.desc())
    )
    if action:
        q = q.where(AuditLog.action == action)
    if user_id:
        q = q.where(AuditLog.user_id == user_id)
    logs = (await db.execute(q.offset(skip).limit(limit))).scalars().all()

    return {
        "stats": {
            "queries_today": queries_today,
            "logins_today": logins_today,
            "active_users_today": active_users_today,
            "total_queries": total_queries,
        },
        "users": [{"id": uid, **info} for uid, info in user_map.items()],
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "user_id": log.user_id,
                "user_email": user_map.get(log.user_id, {}).get("email", "system") if log.user_id else "system",
                "user_role": user_map.get(log.user_id, {}).get("role") if log.user_id else None,
                "timestamp": log.timestamp.isoformat(),
                "metadata": log.log_metadata,
            }
            for log in logs
        ],
    }


@router.get("/tenant")
async def get_tenant_info(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "tenant_id": tenant.id,
        "name": tenant.name,
        "tier": tenant.tier.value,
        "quota_documents": tenant.quota_documents,
        "quota_queries_daily": tenant.quota_queries_daily,
        "llm_provider_override": tenant.llm_provider_override,
    }


# ── Rate-limit config (§27) ─────────────────────────────────────────────────

class RateLimitConfigOut(BaseModel):
    queries_per_minute: int
    queries_per_day: int
    ingestion_per_hour: int
    max_concurrent_queries: int
    is_default: bool  # True if no per-tenant row exists yet (values are platform defaults)


class RateLimitConfigIn(BaseModel):
    queries_per_minute: int = Field(ge=1, le=100_000)
    queries_per_day: int = Field(ge=1, le=10_000_000)
    ingestion_per_hour: int = Field(ge=1, le=1_000_000)
    max_concurrent_queries: int = Field(ge=1, le=10_000)


@router.get("/rate-limit", response_model=RateLimitConfigOut)
async def get_rate_limit(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from src.api.limits import default_limits
    row = (
        await db.execute(
            select(RateLimitConfig).where(RateLimitConfig.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()
    if row is None:
        d = default_limits()
        return RateLimitConfigOut(
            queries_per_minute=d.qpm, queries_per_day=d.qpd,
            ingestion_per_hour=d.ingestion_per_hour, max_concurrent_queries=d.max_concurrent,
            is_default=True,
        )
    return RateLimitConfigOut(
        queries_per_minute=row.queries_per_minute,
        queries_per_day=row.queries_per_day,
        ingestion_per_hour=row.ingestion_per_hour,
        max_concurrent_queries=row.max_concurrent_queries,
        is_default=False,
    )


@router.put("/rate-limit", response_model=RateLimitConfigOut)
async def update_rate_limit(
    body: RateLimitConfigIn,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from src.api.limits import invalidate_tenant_limits
    row = (
        await db.execute(
            select(RateLimitConfig).where(RateLimitConfig.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()
    tenant = (
        await db.execute(select(Tenant).where(Tenant.id == current_user.tenant_id))
    ).scalar_one_or_none()
    tier = tenant.tier.value if tenant else "starter"
    if row is None:
        row = RateLimitConfig(tenant_id=current_user.tenant_id, tier=tier)
        db.add(row)
    row.tier = tier
    row.queries_per_minute = body.queries_per_minute
    row.queries_per_day = body.queries_per_day
    row.ingestion_per_hour = body.ingestion_per_hour
    row.max_concurrent_queries = body.max_concurrent_queries
    await db.commit()
    # Drop the cached limits so the change takes effect on the next request.
    await invalidate_tenant_limits(current_user.tenant_id)
    return RateLimitConfigOut(
        queries_per_minute=row.queries_per_minute,
        queries_per_day=row.queries_per_day,
        ingestion_per_hour=row.ingestion_per_hour,
        max_concurrent_queries=row.max_concurrent_queries,
        is_default=False,
    )
