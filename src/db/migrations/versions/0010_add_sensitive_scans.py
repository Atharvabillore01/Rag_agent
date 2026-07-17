"""add sensitive_scans table

Revision ID: 0010_add_sensitive_scans
Revises: 0009_add_contention_analyses
Create Date: 2026-07-17

Sensitive-data scan / PII (feature-implementation-plan §28). Idempotent —
creates the table only if missing. Stores only masked findings (no raw PII).
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0010_add_sensitive_scans"
down_revision = "0009_add_contention_analyses"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(t: str) -> bool:
    return t in _insp().get_table_names()


def upgrade() -> None:
    if not _has_table("sensitive_scans"):
        op.create_table(
            "sensitive_scans",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("document_ids", sa.JSON(), nullable=False),
            sa.Column("results", sa.JSON(), nullable=True),
            sa.Column("summary", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_sensitive_scans_tenant_id", "sensitive_scans", ["tenant_id"])
        op.create_index(
            "ix_sensitive_scans_tenant_created", "sensitive_scans", ["tenant_id", "created_at"]
        )


def downgrade() -> None:
    if _has_table("sensitive_scans"):
        op.drop_index("ix_sensitive_scans_tenant_created", table_name="sensitive_scans")
        op.drop_index("ix_sensitive_scans_tenant_id", table_name="sensitive_scans")
        op.drop_table("sensitive_scans")
