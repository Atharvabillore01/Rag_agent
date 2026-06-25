"""Auth endpoints — login, register, token refresh."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import create_access_token, hash_password, verify_password
from src.db.models import AuditLog, Tenant, TenantTier, User, UserRole
from src.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    tenant = Tenant(name=body.tenant_name, tier=TenantTier.starter)
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role=UserRole.org_admin,
    )
    db.add(user)
    await db.flush()

    token = create_access_token({"sub": str(user.id), "tenant_id": str(tenant.id), "role": user.role.value, "email": user.email})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(User).where(User.email == body.email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="user_login",
        resource_type="session",
        log_metadata={"email": user.email},
    ))
    await db.commit()

    token = create_access_token({"sub": str(user.id), "tenant_id": str(user.tenant_id), "role": user.role.value, "email": user.email})
    return TokenResponse(access_token=token)
