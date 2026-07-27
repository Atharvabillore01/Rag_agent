"""add clinic_notifications table

Revision ID: 0016_add_clinic_notifications
Revises: 0015_add_clinic_tables
Create Date: 2026-07-20

Clinic real-time notifications (feature-implementation-plan §33 P2). Idempotent.
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_add_clinic_notifications"
down_revision = "0015_add_clinic_tables"
branch_labels = None
depends_on = None


def _has_table(t: str) -> bool:
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("clinic_notifications"):
        op.create_table(
            "clinic_notifications",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("recipient_user_id", sa.String(length=36), nullable=False),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["recipient_user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_clinic_notifications_recipient", "clinic_notifications",
                        ["tenant_id", "recipient_user_id", "read"])


def downgrade() -> None:
    if _has_table("clinic_notifications"):
        op.drop_table("clinic_notifications")
