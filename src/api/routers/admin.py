"""Admin endpoints — user management, tenant config, audit log (§6, §11)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
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
    from src.api.auth import hash_password

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
