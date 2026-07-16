"""Auth endpoints — login, register, token refresh."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api import totp
from src.api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    revoke_token,
    validate_password,
    verify_password,
)
from src.config import get_settings
from src.db.models import AuditLog, Tenant, TenantTier, User, UserRole
from src.db.session import get_db
from src.domains import DEFAULT_DOMAIN, DOMAINS, is_known_domain
from src.storage.cache import get_cache

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
_bearer = HTTPBearer()


def _registration_allowed(email: str) -> bool:
    """G5: self-serve registration is gated. Open only if explicitly enabled, or
    if the email's domain is on the allowlist."""
    if settings.allow_open_registration:
        return True
    allowed = [d.strip().lower() for d in (settings.registration_allowed_domains or [])]
    if not allowed:
        return False
    return email.rsplit("@", 1)[-1].lower() in allowed


def _client_ip(request: Request) -> str:
    # Honor a single proxy hop; fall back to the socket peer.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _throttle_auth(request: Request, bucket: str) -> None:
    """G6: per-IP sliding-window throttle for unauthenticated auth endpoints."""
    ip = _client_ip(request)
    key = f"authrl:{bucket}:{ip}:{int(time.time() // 60)}"
    allowed, _ = await get_cache().rate_limit_check(
        key, settings.auth_rate_limit_per_minute, window_seconds=60
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait a minute and try again.",
            headers={"Retry-After": "60"},
        )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_name: str
    # Vertical this workspace runs (multi-domain plan §3). Optional — omitting it
    # yields a "generic" workspace, identical to the pre-domain-pack behavior.
    domain: str = DEFAULT_DOMAIN


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None   # required when the account has MFA enabled


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCodeRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await _throttle_auth(request, "register")
    # G5: registration creates a new tenant + org_admin, so it is gated by default.
    if not _registration_allowed(body.email):
        raise HTTPException(
            status_code=403,
            detail="Self-serve registration is disabled. Contact your administrator.",
        )

    # G15: enforce the password policy before doing any work.
    try:
        validate_password(body.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Normalize case ("Legal" -> "legal") but reject genuinely unknown domains so
    # a typo surfaces here instead of silently creating a mis-configured tenant.
    domain = body.domain.strip().lower()
    if not is_known_domain(domain):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown domain {body.domain!r}. Known domains: {sorted(DOMAINS)}",
        )

    tenant = Tenant(name=body.tenant_name, tier=TenantTier.starter, domain=domain)
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

    # G13: audit tenant provisioning (with caller IP + user-agent).
    db.add(AuditLog(
        tenant_id=tenant.id,
        user_id=user.id,
        action="tenant_create",
        resource_type="tenant",
        resource_id=tenant.id,
        log_metadata={
            "tenant_name": body.tenant_name,
            "domain": tenant.domain,
            "ip": _client_ip(request),
            "user_agent": request.headers.get("user-agent", "")[:200],
        },
    ))

    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": str(tenant.id),
        "role": user.role.value,
        "email": user.email,
        "domain": tenant.domain,
    })
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await _throttle_auth(request, "login")
    result = await db.execute(
        select(User).where(User.email == body.email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password or not verify_password(body.password, user.hashed_password):
        # G6: audit a wrong-password attempt on a real account (brute-force signal).
        # Unknown emails aren't logged — there's no tenant to attribute them to,
        # and not confirming existence avoids account enumeration.
        if user:
            db.add(AuditLog(
                tenant_id=user.tenant_id,
                user_id=user.id,
                action="user_login_failed",
                resource_type="session",
                log_metadata={"email": user.email},
            ))
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # G10: second factor. Password is correct; if MFA is on, a valid TOTP code
    # is also required. A distinct 401 detail lets the client prompt for the code.
    if user.mfa_enabled:
        if not body.mfa_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA code required")
        if not totp.verify_totp(user.mfa_secret or "", body.mfa_code):
            db.add(AuditLog(
                tenant_id=user.tenant_id, user_id=user.id, action="user_login_failed",
                resource_type="session", log_metadata={"email": user.email, "reason": "mfa"},
            ))
            await db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid MFA code")

    user.last_login_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="user_login",
        resource_type="session",
        log_metadata={"email": user.email},
    ))
    await db.commit()

    # Carry the tenant's domain in the token so the client can theme/route by
    # vertical. Fall back to the default if the tenant row is somehow missing.
    tenant = await db.get(Tenant, user.tenant_id)
    token = create_access_token({
        "sub": str(user.id),
        "tenant_id": str(user.tenant_id),
        "role": user.role.value,
        "email": user.email,
        "domain": tenant.domain if tenant else DEFAULT_DOMAIN,
    })
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=204)
async def logout(credentials: HTTPAuthorizationCredentials = Depends(_bearer)):
    """G14: revoke the presented token (jti denylist) so it can't be reused."""
    await revoke_token(credentials.credentials)


# ── MFA (G10) ─────────────────────────────────────────────────────────────────

@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def mfa_setup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Begin TOTP enrollment: generate a secret and return the otpauth URI. MFA is
    not active until a code is confirmed via /mfa/verify."""
    if current_user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is already enabled. Disable it first to re-enroll.")
    secret = totp.generate_secret()
    current_user.mfa_secret = secret
    current_user.mfa_enabled = False
    await db.commit()
    return MfaSetupResponse(secret=secret, otpauth_uri=totp.provisioning_uri(secret, current_user.email))


@router.post("/mfa/verify")
async def mfa_verify(
    body: MfaCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Confirm enrollment with a code from the authenticator; enables MFA."""
    if not current_user.mfa_secret:
        raise HTTPException(status_code=400, detail="No MFA enrollment in progress. Call /auth/mfa/setup first.")
    if not totp.verify_totp(current_user.mfa_secret, body.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code.")
    current_user.mfa_enabled = True
    await db.commit()
    return {"mfa_enabled": True}


@router.post("/mfa/disable")
async def mfa_disable(
    body: MfaCodeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable MFA (requires a current valid code)."""
    if not current_user.mfa_enabled:
        raise HTTPException(status_code=400, detail="MFA is not enabled.")
    if not totp.verify_totp(current_user.mfa_secret or "", body.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code.")
    current_user.mfa_secret = None
    current_user.mfa_enabled = False
    await db.commit()
    return {"mfa_enabled": False}
