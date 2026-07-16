"""add redlines table

Revision ID: 0003_add_redlines
Revises: 0002_add_parallel_reviews
Create Date: 2026-07-15

Creates the ``redlines`` table backing the Redline / document-diff feature
(feature-implementation-plan §8). Idempotent — creates the table only if missing,
so it is safe against a schema bootstrapped by create_tables.py.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0003_add_redlines"
down_revision = "0002_add_parallel_reviews"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("redlines"):
        return
    op.create_table(
        "redlines",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("base_document_id", sa.String(length=36), nullable=False),
        sa.Column("revised_document_id", sa.String(length=36), nullable=False),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_redlines_tenant_id", "redlines", ["tenant_id"])
    op.create_index("ix_redlines_tenant_created", "redlines", ["tenant_id", "created_at"])


def downgrade() -> None:
    if not _has_table("redlines"):
        return
    op.drop_index("ix_redlines_tenant_created", table_name="redlines")
    op.drop_index("ix_redlines_tenant_id", table_name="redlines")
    op.drop_table("redlines")
