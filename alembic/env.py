"""Alembic environment for nous.

URL resolution order:

1. ``alembic -x url=sqlite:///...`` (``context.get_x_argument``).
2. ``NOUS_DB_URL`` environment variable.
3. ``sqlalchemy.url`` from ``alembic.ini``.

The third source is the developer-local default; production deployments
should set either of the first two so the migration hits the deployment
DB rather than the local sandbox.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import the models so SQLModel.metadata is populated.
from nous import db  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _resolve_url() -> str | None:
    x_args = dict(
        arg.split("=", 1) for arg in context.get_x_argument() if "=" in arg
    )
    url = x_args.get("url") or os.environ.get("NOUS_DB_URL")
    if url:
        return url
    return config.get_main_option("sqlalchemy.url")


_resolved_url = _resolve_url()
if _resolved_url:
    # ConfigParser does %-interpolation; escape % so a percent-encoded URL
    # (an encoded password or path) does not raise on read (BL-051, ADR 0037).
    config.set_main_option("sqlalchemy.url", _resolved_url.replace("%", "%%"))
    if _resolved_url.startswith("sqlite:///"):
        sqlite_path = Path(_resolved_url[len("sqlite:///"):])
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
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
