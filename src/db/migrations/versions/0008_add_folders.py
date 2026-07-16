"""add folders table + documents.folder_id

Revision ID: 0008_add_folders
Revises: 0007_add_user_mfa
Create Date: 2026-07-17

Folders / matter organization (feature-implementation-plan §23). Idempotent —
creates the table and column only if missing.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0008_add_folders"
down_revision = "0007_add_user_mfa"
branch_labels = None
depends_on = None


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(t: str) -> bool:
    return t in _insp().get_table_names()


def _has_column(t: str, c: str) -> bool:
    return t in _insp().get_table_names() and c in {col["name"] for col in _insp().get_columns(t)}


def upgrade() -> None:
    if not _has_table("folders"):
        op.create_table(
            "folders",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            sa.Column("created_by", sa.String(length=36), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        )
        op.create_index("ix_folders_tenant_id", "folders", ["tenant_id"])

    if _has_table("documents") and not _has_column("documents", "folder_id"):
        op.add_column("documents", sa.Column("folder_id", sa.String(length=36), nullable=True))
        op.create_foreign_key(
            "fk_documents_folder_id", "documents", "folders",
            ["folder_id"], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    if _has_column("documents", "folder_id"):
        op.drop_constraint("fk_documents_folder_id", "documents", type_="foreignkey")
        op.drop_column("documents", "folder_id")
    if _has_table("folders"):
        op.drop_index("ix_folders_tenant_id", table_name="folders")
        op.drop_table("folders")
