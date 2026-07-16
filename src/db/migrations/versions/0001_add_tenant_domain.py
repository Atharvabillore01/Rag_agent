"""add tenants.domain column

Revision ID: 0001_add_tenant_domain
Revises:
Create Date: 2026-07-15

Adds the per-tenant vertical `domain` field (multi-domain plan §3) that selects
which domain pack — prompts, skills, citation sources, extraction schemas — a
tenant runs. Defaults to "generic", which behaves exactly like the platform did
before domain packs existed.

This repo historically bootstraps its schema via `create_tables.py`
(`Base.metadata.create_all`), so there is no prior Alembic baseline — hence
`down_revision = None`. The migration is deliberately forward-only and
*idempotent*: it inspects the live schema first and only alters what is actually
missing. That makes it safe to run against a database created either way:

  * bootstrapped by create_tables.py BEFORE this change  -> column added
  * bootstrapped by create_tables.py AFTER this change    -> column already
    present, so `upgrade()` is a no-op
  * empty database with no tables yet                      -> no-op (nothing to
    alter; create_tables.py is expected to run first)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0001_add_tenant_domain"
down_revision = None
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in _inspector().get_columns(table)}


def upgrade() -> None:
    if not _has_table("tenants"):
        # Schema not bootstrapped yet — create_tables.py will build tenants with
        # the column already defined on the model. Nothing to do here.
        return
    if not _has_column("tenants", "domain"):
        op.add_column(
            "tenants",
            sa.Column(
                "domain",
                sa.String(length=50),
                nullable=False,
                server_default="generic",
            ),
        )


def downgrade() -> None:
    if _has_table("tenants") and _has_column("tenants", "domain"):
        op.drop_column("tenants", "domain")
