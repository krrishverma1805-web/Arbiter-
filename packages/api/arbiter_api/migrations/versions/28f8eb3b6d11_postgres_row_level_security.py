"""postgres row level security

Row-level security on every tenant-scoped table (Postgres only — a no-op on
SQLite). Even a query that forgets its `WHERE org_id = …` filter cannot cross a
tenant: `EventStore` / the auth layer `SET arbiter.org_id` per session and the
policy restricts every row to that value. Defense in depth behind the
application-level filtering.

Revision ID: 28f8eb3b6d11
Revises: 5c450dd7dfdc
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "28f8eb3b6d11"
down_revision: str | None = "5c450dd7dfdc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = ("events", "jobs", "idempotency_keys")


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {t}_tenant_isolation ON {t} USING "
            "(org_id = current_setting('arbiter.org_id', true)) "
            "WITH CHECK (org_id = current_setting('arbiter.org_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {t}_tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
