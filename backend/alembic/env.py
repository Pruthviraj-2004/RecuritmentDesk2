from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import text

import app.models  # noqa: F401  (registers all tables on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
settings = get_settings()


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        schema = settings.database_schema if engine.dialect.name == "postgresql" else None
        if schema:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True, version_table_schema=schema)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
