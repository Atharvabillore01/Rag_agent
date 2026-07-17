"""add contention_analyses table

Revision ID: 0009_add_contention_analyses
Revises: 0008_add_folders
Create Date: 2026-07-17

Contentions Comparison / pleadings analysis (feature-implementation-plan §26).
Idempotent — creates the table only if missing.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0009_add_contention_analyses"
down_revision = "0008_add_folders"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(t: str) -> bool:
    return t in _insp().get_table_names()


def upgrade() -> None:
    if not _has_table("contention_analyses"):
        op.create_table(
            "contention_analyses",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("document_ids", sa.JSON(), nullable=False),
            sa.Column("issues", sa.JSON(), nullable=True),
            sa.Column("results", sa.JSON(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_contention_analyses_tenant_id", "contention_analyses", ["tenant_id"])
        op.create_index(
            "ix_contention_analyses_tenant_created",
            "contention_analyses",
            ["tenant_id", "created_at"],
        )


def downgrade() -> None:
    if _has_table("contention_analyses"):
        op.drop_index("ix_contention_analyses_tenant_created", table_name="contention_analyses")
        op.drop_index("ix_contention_analyses_tenant_id", table_name="contention_analyses")
        op.drop_table("contention_analyses")
