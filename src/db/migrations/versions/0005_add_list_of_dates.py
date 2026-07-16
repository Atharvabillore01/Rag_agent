"""add list_of_dates table

Revision ID: 0005_add_list_of_dates
Revises: 0004_add_translations
Create Date: 2026-07-15

Creates the ``list_of_dates`` table backing the LoD Builder feature
(feature-implementation-plan §11). Idempotent — creates the table only if missing.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005_add_list_of_dates"
down_revision = "0004_add_translations"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("list_of_dates"):
        return
    op.create_table(
        "list_of_dates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_list_of_dates_tenant_id", "list_of_dates", ["tenant_id"])
    op.create_index("ix_list_of_dates_tenant_created", "list_of_dates", ["tenant_id", "created_at"])


def downgrade() -> None:
    if not _has_table("list_of_dates"):
        return
    op.drop_index("ix_list_of_dates_tenant_created", table_name="list_of_dates")
    op.drop_index("ix_list_of_dates_tenant_id", table_name="list_of_dates")
    op.drop_table("list_of_dates")
