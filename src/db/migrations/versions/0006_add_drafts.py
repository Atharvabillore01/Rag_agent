"""add drafts table

Revision ID: 0006_add_drafts
Revises: 0005_add_list_of_dates
Create Date: 2026-07-15

Creates the ``drafts`` table backing the Drafting assistant feature
(feature-implementation-plan §13). Idempotent — creates the table only if missing.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006_add_drafts"
down_revision = "0005_add_list_of_dates"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("drafts"):
        return
    op.create_table(
        "drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_drafts_tenant_id", "drafts", ["tenant_id"])
    op.create_index("ix_drafts_tenant_created", "drafts", ["tenant_id", "created_at"])


def downgrade() -> None:
    if not _has_table("drafts"):
        return
    op.drop_index("ix_drafts_tenant_created", table_name="drafts")
    op.drop_index("ix_drafts_tenant_id", table_name="drafts")
    op.drop_table("drafts")
