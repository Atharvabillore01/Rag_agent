"""add clinic roles (reception, doctor) to userrole enum

Revision ID: 0014_add_clinic_roles
Revises: 0013_add_platform_admin
Create Date: 2026-07-19

Clinic vertical (feature-implementation-plan §33). Postgres 12+ allows
ALTER TYPE ... ADD VALUE inside a transaction as long as the value isn't used in
the same transaction (it isn't here). Idempotent via IF NOT EXISTS.
"""

from alembic import op

revision = "0014_add_clinic_roles"
down_revision = "0013_add_platform_admin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'reception'")
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'doctor'")


def downgrade() -> None:
    # Removing an enum value is unsafe (may be referenced by rows) — no-op.
    pass
