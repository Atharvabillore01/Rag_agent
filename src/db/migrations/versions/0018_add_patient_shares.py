"""add patient_shares table

Revision ID: 0018_add_patient_shares
Revises: 0017_add_clinic_visits
Create Date: 2026-07-20

Clinic team sharing (feature-implementation-plan §33 P4). Idempotent.
"""

from alembic import op
import sqlalchemy as sa

revision = "0018_add_patient_shares"
down_revision = "0017_add_clinic_visits"
branch_labels = None
depends_on = None


def _has_table(t: str) -> bool:
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("patient_shares"):
        op.create_table(
            "patient_shares",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("patient_id", sa.String(length=36), nullable=False),
            sa.Column("doctor_user_id", sa.String(length=36), nullable=False),
            sa.Column("shared_by", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["doctor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["shared_by"], ["users.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("patient_id", "doctor_user_id", name="uq_patient_share"),
        )
        op.create_index("ix_patient_shares_doctor", "patient_shares", ["tenant_id", "doctor_user_id"])


def downgrade() -> None:
    if _has_table("patient_shares"):
        op.drop_table("patient_shares")
