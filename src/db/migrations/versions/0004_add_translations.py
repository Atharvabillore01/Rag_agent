"""add translations table

Revision ID: 0004_add_translations
Revises: 0003_add_redlines
Create Date: 2026-07-15

Creates the ``translations`` table backing the Document Translation feature
(feature-implementation-plan §9). Idempotent — creates the table only if missing.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0004_add_translations"
down_revision = "0003_add_redlines"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def upgrade() -> None:
    if _has_table("translations"):
        return
    op.create_table(
        "translations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=True),
        sa.Column("target_language", sa.String(length=80), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_translations_tenant_id", "translations", ["tenant_id"])
    op.create_index("ix_translations_tenant_created", "translations", ["tenant_id", "created_at"])


def downgrade() -> None:
    if not _has_table("translations"):
        return
    op.drop_index("ix_translations_tenant_created", table_name="translations")
    op.drop_index("ix_translations_tenant_id", table_name="translations")
    op.drop_table("translations")
