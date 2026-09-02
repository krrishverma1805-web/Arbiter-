"""The Alembic migrations must never drift from the SQLModel models
(docs/28 §2). `alembic upgrade head` on an empty database has to produce exactly
the schema `SQLModel.metadata.create_all` would."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _schema(db_path: str) -> list[tuple[str, str]]:
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            "SELECT type, name FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND name != 'alembic_version' "
            "ORDER BY type, name"
        ).fetchall()
    finally:
        con.close()
    return sorted(rows)


def test_migrations_match_the_models(tmp_path: Path):
    import arbiter_api.auth  # noqa: F401
    import arbiter_api.jobs  # noqa: F401
    import arbiter_engine.events.store  # noqa: F401
    from arbiter_api.migrations import upgrade
    from sqlmodel import SQLModel, create_engine

    mig_db = tmp_path / "migrated.db"
    upgrade(f"sqlite:///{mig_db}")

    model_db = tmp_path / "models.db"
    SQLModel.metadata.create_all(create_engine(f"sqlite:///{model_db}"))

    assert _schema(str(mig_db)) == _schema(str(model_db))


def test_upgrade_is_idempotent(tmp_path: Path):
    from arbiter_api.migrations import upgrade

    db = f"sqlite:///{tmp_path / 'x.db'}"
    upgrade(db)
    upgrade(db)  # second run is a no-op, must not raise
