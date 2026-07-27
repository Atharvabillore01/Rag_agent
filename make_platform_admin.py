"""Create or promote a PLATFORM ADMIN — works on a non-empty database.

Unlike seed_admin.py (which only seeds an empty DB), this always ensures the given
email is an active platform admin: it promotes an existing user (resetting the
password) or creates a new tenant + platform-admin user.

    SEED_TENANT_NAME='Acme'  SEED_ADMIN_EMAIL='you@company.com' \
    SEED_ADMIN_PASSWORD='StrongPass123'  PYTHONPATH=. .venv/bin/python make_platform_admin.py
"""

import asyncio
import os

TENANT_NAME = os.getenv("SEED_TENANT_NAME", "Platform Org")
EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "changeme123")


async def main():
    from sqlalchemy import select

    from src.api.auth import hash_password
    from src.db.models import Tenant, TenantTier, User, UserRole
    from src.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == EMAIL))).scalars().first()
        if user is not None:
            user.is_platform_admin = True
            user.is_active = True
            user.hashed_password = hash_password(PASSWORD)
            await db.commit()
            print(f"Promoted existing user {EMAIL!r} to platform admin (password reset).")
        else:
            tenant = Tenant(name=TENANT_NAME, tier=TenantTier.pro, quota_documents=10_000)
            db.add(tenant)
            await db.flush()
            admin = User(
                tenant_id=tenant.id, email=EMAIL, hashed_password=hash_password(PASSWORD),
                role=UserRole.org_admin, is_active=True, is_platform_admin=True,
            )
            db.add(admin)
            await db.commit()
            print(f"Created tenant {TENANT_NAME!r} + platform admin {EMAIL!r}.")

    print("Sign in at  /platform/login  with that email + password.")


if __name__ == "__main__":
    asyncio.run(main())
