"""add parallel_reviews table

Revision ID: 0002_add_parallel_reviews
Revises: 0001_add_tenant_domain
Create Date: 2026-07-15

Creates the ``parallel_reviews`` table backing the Parallel Review feature
(feature-implementation-plan §3): a saved "N documents × M questions → answers"
run. Idempotent and safe against a schema bootstrapped by create_tables.py — it
creates the table only if it is missing.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_parallel_reviews"
down_revision = "0001_add_tenant_domain"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("parallel_reviews"):
        return
    op.create_table(
        "parallel_reviews",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("questions", sa.JSON(), nullable=False),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_parallel_reviews_tenant_id", "parallel_reviews", ["tenant_id"])
    op.create_index(
        "ix_parallel_reviews_tenant_created", "parallel_reviews", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    if not _has_table("parallel_reviews"):
        return
    op.drop_index("ix_parallel_reviews_tenant_created", table_name="parallel_reviews")
    op.drop_index("ix_parallel_reviews_tenant_id", table_name="parallel_reviews")
    op.drop_table("parallel_reviews")
