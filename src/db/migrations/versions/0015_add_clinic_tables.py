"""add clinic tables (doctor_profiles, patients, queue_entries, follow_ups, reception_assignments)

Revision ID: 0015_add_clinic_tables
Revises: 0014_add_clinic_roles
Create Date: 2026-07-19

Clinic vertical (feature-implementation-plan §33). Idempotent.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0015_add_clinic_tables"
down_revision = "0014_add_clinic_roles"
branch_labels = None
depends_on = None

# create_type=False: the types are created explicitly (idempotent DO blocks below),
# so create_table only REFERENCES them and never re-emits CREATE TYPE.
_doctorstatus = postgresql.ENUM("available", "busy", "away", name="doctorstatus", create_type=False)
_queuestatus = postgresql.ENUM("waiting", "in_progress", "done", "cancelled", name="queuestatus", create_type=False)


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(t: str) -> bool:
    return t in _insp().get_table_names()


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='doctorstatus') "
        "THEN CREATE TYPE doctorstatus AS ENUM ('available','busy','away'); END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname='queuestatus') "
        "THEN CREATE TYPE queuestatus AS ENUM ('waiting','in_progress','done','cancelled'); END IF; END $$;"
    )

    if not _has_table("doctor_profiles"):
        op.create_table(
            "doctor_profiles",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("specialty", sa.String(length=255), nullable=True),
            sa.Column("room", sa.String(length=50), nullable=True),
            sa.Column("status", _doctorstatus, nullable=False, server_default="available"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("user_id", name="uq_doctor_profile_user"),
        )
        op.create_index("ix_doctor_profiles_tenant_id", "doctor_profiles", ["tenant_id"])

    if not _has_table("patients"):
        op.create_table(
            "patients",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("phone", sa.String(length=40), nullable=True),
            sa.Column("dob", sa.String(length=20), nullable=True),
            sa.Column("details", sa.JSON(), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_patients_tenant_id", "patients", ["tenant_id"])
        op.create_index("ix_patients_tenant_created", "patients", ["tenant_id", "created_at"])

    if not _has_table("queue_entries"):
        op.create_table(
            "queue_entries",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("patient_id", sa.String(length=36), nullable=False),
            sa.Column("doctor_user_id", sa.String(length=36), nullable=False),
            sa.Column("status", _queuestatus, nullable=False, server_default="waiting"),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("called_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["doctor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_queue_entries_tenant_id", "queue_entries", ["tenant_id"])
        op.create_index("ix_queue_entries_doctor_status", "queue_entries", ["tenant_id", "doctor_user_id", "status"])

    if not _has_table("follow_ups"):
        op.create_table(
            "follow_ups",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("patient_id", sa.String(length=36), nullable=False),
            sa.Column("doctor_user_id", sa.String(length=36), nullable=False),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["doctor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_follow_ups_tenant_id", "follow_ups", ["tenant_id"])
        op.create_index("ix_follow_ups_tenant_scheduled", "follow_ups", ["tenant_id", "scheduled_at"])

    if not _has_table("reception_assignments"):
        op.create_table(
            "reception_assignments",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("reception_user_id", sa.String(length=36), nullable=False),
            sa.Column("doctor_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reception_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["doctor_user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("tenant_id", "reception_user_id", name="uq_reception_assignment"),
        )
        op.create_index("ix_reception_assignments_tenant_id", "reception_assignments", ["tenant_id"])


def downgrade() -> None:
    for t in ("reception_assignments", "follow_ups", "queue_entries", "patients", "doctor_profiles"):
        if _has_table(t):
            op.drop_table(t)
    bind = op.get_bind()
    _queuestatus.drop(bind, checkfirst=True)
    _doctorstatus.drop(bind, checkfirst=True)
