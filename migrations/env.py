"""Alembic migrations for SQLite development and PostgreSQL deployment."""
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from roadwatch.db import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
url = os.environ.get("ROADWATCH_DATABASE_URL", "sqlite:///./roadwatch.db")
target_metadata = Base.metadata


def offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def online():
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    offline()
else:
    online()
