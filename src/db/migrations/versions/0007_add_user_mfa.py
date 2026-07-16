"""add user MFA columns (mfa_secret, mfa_enabled)

Revision ID: 0007_add_user_mfa
Revises: 0006_add_drafts
Create Date: 2026-07-15

Adds TOTP MFA fields to users (G10). Idempotent per-column, so it is safe against
a schema bootstrapped by create_tables.py.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0007_add_user_mfa"
down_revision = "0006_add_drafts"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    insp = sa.inspect(op.get_bind())
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    cols = _cols("users")
    if not cols:
        return  # users table not bootstrapped yet
    if "mfa_secret" not in cols:
        op.add_column("users", sa.Column("mfa_secret", sa.Text(), nullable=True))
    if "mfa_enabled" not in cols:
        op.add_column(
            "users",
            sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )


def downgrade() -> None:
    cols = _cols("users")
    if "mfa_enabled" in cols:
        op.drop_column("users", "mfa_enabled")
    if "mfa_secret" in cols:
        op.drop_column("users", "mfa_secret")
