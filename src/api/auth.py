"""JWT-based authentication helpers (§6, §15)."""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.db.models import User, UserRole
from src.db.session import get_db

_bearer = HTTPBearer()
_settings = get_settings()

ALGORITHM = "HS256"


class PasswordPolicyError(ValueError):
    """Raised when a password fails the policy (G15)."""


def validate_password(password: str) -> None:
    """G15: enforce a minimum length and reject passwords longer than bcrypt's
    72-byte limit (beyond which bcrypt silently truncates, giving a false sense
    of strength and inconsistent verification)."""
    if len(password) < _settings.min_password_length:
        raise PasswordPolicyError(
            f"Password must be at least {_settings.min_password_length} characters."
        )
    if len(password.encode("utf-8")) > 72:
        raise PasswordPolicyError("Password must be at most 72 bytes long.")


def hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode(), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


class TokenData(BaseModel):
    user_id: str
    tenant_id: str
    role: str


def create_access_token(data: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        **data,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=_settings.access_token_expire_minutes),
        "iss": _settings.jwt_issuer,
        "aud": _settings.jwt_audience,
        "jti": data.get("jti") or str(uuid.uuid4()),
    }
    return jwt.encode(payload, _settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode + verify a token, including issuer and audience (and exp/nbf/iat)."""
    return jwt.decode(
        token,
        _settings.secret_key,
        algorithms=[ALGORITHM],
        audience=_settings.jwt_audience,
        issuer=_settings.jwt_issuer,
    )


async def revoke_token(token: str) -> None:
    """G14: add a token's jti to the denylist until it would expire (logout)."""
    try:
        payload = decode_token(token)
    except JWTError:
        return  # already invalid/expired — nothing to revoke
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    ttl = int(exp - datetime.now(timezone.utc).timestamp())
    from src.storage.cache import get_cache
    await get_cache().revoke_jti(jti, ttl)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        user_id: str = payload.get("sub", "")
        jti: str = payload.get("jti", "")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # G14: reject revoked (logged-out) tokens. Fails open on a Redis outage.
    if jti:
        from src.storage.cache import get_cache
        if await get_cache().is_jti_revoked(jti):
            raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise credentials_exception
    return user


def require_role(*roles: UserRole):
    """Factory for role-enforcement dependencies."""
    async def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role {user.role!r} is not allowed for this operation.",
            )
        return user
    return _check


# Convenience dependencies
require_admin = require_role(UserRole.org_admin)
require_editor = require_role(UserRole.org_admin, UserRole.editor)
require_viewer = require_role(UserRole.org_admin, UserRole.editor, UserRole.viewer, UserRole.demo)
