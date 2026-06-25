"""Bootstrap script — creates the first tenant and admin user.

Run once after create_tables.py:
    python seed_admin.py

Override defaults via environment variables or just edit the constants below.
"""

import asyncio
import os
import sys


TENANT_NAME = os.getenv("SEED_TENANT_NAME", "Default Org")
ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "changeme123")


async def main():
    from sqlalchemy import select

    from src.api.auth import hash_password
    from src.db.models import Tenant, TenantTier, User, UserRole
    from src.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # Check if already seeded
        existing = await db.execute(select(Tenant).limit(1))
        if existing.scalar_one_or_none():
            print("Database already has tenants — skipping seed.")
            print("Use POST /admin/users to create additional users.")
            return

        tenant = Tenant(
            name=TENANT_NAME,
            tier=TenantTier.pro,
            quota_documents=10_000,
        )
        db.add(tenant)
        await db.flush()  # get tenant.id

        admin = User(
            tenant_id=tenant.id,
            email=ADMIN_EMAIL,
            hashed_password=hash_password(ADMIN_PASSWORD),
            role=UserRole.org_admin,
            is_active=True,
        )
        db.add(admin)
        await db.commit()

    print(f"Created tenant: {TENANT_NAME!r} (id={tenant.id})")
    print(f"Created admin:  {ADMIN_EMAIL!r}")
    print(f"Password:        {ADMIN_PASSWORD!r}")
    print()
    print("Next: POST /auth/login  with those credentials to get a JWT token.")


if __name__ == "__main__":
    asyncio.run(main())
