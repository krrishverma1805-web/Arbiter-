"""Alembic migrations for the Arbiter database (docs/28 §2/§3).

`arbiter-api db upgrade` runs `alembic upgrade head`. The schema is the union of
every SQLModel `table=True` across the engine + api (`events`, `api_keys`,
`jobs`). `test_migrations.py` asserts `alembic upgrade head` produces exactly the
schema `SQLModel.metadata.create_all` would — so the migrations can never drift
from the models.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

_HERE = Path(__file__).parent


def alembic_config(db_url: str | None = None) -> Config:
    import os

    cfg = Config()
    cfg.set_main_option("script_location", str(_HERE))
    cfg.set_main_option(
        "sqlalchemy.url",
        db_url or os.environ.get("ARBITER_DB_URL", "sqlite:///./data/arbiter.db"),
    )
    return cfg


def upgrade(db_url: str | None = None, revision: str = "head") -> None:
    from alembic import command

    command.upgrade(alembic_config(db_url), revision)


def current(db_url: str | None = None) -> None:
    from alembic import command

    command.current(alembic_config(db_url), verbose=True)
