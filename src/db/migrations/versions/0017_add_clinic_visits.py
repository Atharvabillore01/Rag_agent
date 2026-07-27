"""add clinic_visits table

Revision ID: 0017_add_clinic_visits
Revises: 0016_add_clinic_notifications
Create Date: 2026-07-20

Clinic visits + AI insights (feature-implementation-plan §33 P3). notes stored as
Text (EncryptedText at the ORM layer). Idempotent.
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_add_clinic_visits"
down_revision = "0016_add_clinic_notifications"
branch_labels = None
depends_on = None


def _has_table(t: str) -> bool:
    return t in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _has_table("clinic_visits"):
        op.create_table(
            "clinic_visits",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("patient_id", sa.String(length=36), nullable=False),
            sa.Column("doctor_user_id", sa.String(length=36), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("ai_insights", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["doctor_user_id"], ["users.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_clinic_visits_patient", "clinic_visits", ["tenant_id", "patient_id"])
        op.create_index("ix_clinic_visits_doctor_created", "clinic_visits", ["tenant_id", "doctor_user_id", "created_at"])


def downgrade() -> None:
    if _has_table("clinic_visits"):
        op.drop_table("clinic_visits")
