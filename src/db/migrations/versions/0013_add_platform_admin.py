"""add users.is_platform_admin

Revision ID: 0013_add_platform_admin
Revises: 0012_add_playbook_reviews
Create Date: 2026-07-17

Platform super-admin flag (feature-implementation-plan §31). Idempotent.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0013_add_platform_admin"
down_revision = "0012_add_playbook_reviews"
branch_labels = None
depends_on = None


def _has_column(t: str, c: str) -> bool:
    insp = sa.inspect(op.get_bind())
    return t in insp.get_table_names() and c in {col["name"] for col in insp.get_columns(t)}


def upgrade() -> None:
    if not _has_column("users", "is_platform_admin"):
        op.add_column(
            "users",
            sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    if _has_column("users", "is_platform_admin"):
        op.drop_column("users", "is_platform_admin")
