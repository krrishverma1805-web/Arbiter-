from __future__ import annotations

import arbiter_engine.events.store  # noqa: F401  (Event)
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# import every module that defines a `table=True` model so metadata is complete
import arbiter_api.auth  # noqa: F401  (ApiKey)
import arbiter_api.jobs  # noqa: F401  (Job)

target_metadata = SQLModel.metadata
config = context.config


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
