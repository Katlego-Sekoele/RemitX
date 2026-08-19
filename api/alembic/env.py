"""Alembic environment.

The database URL and the target metadata both come from the application, so
migrations can never drift from the app's own configuration:

  URL       remitx_api.config.Config.DATABASE_URL (root .env, or DATABASE_URL)
  Metadata  remitx_api.extensions.Base, with every ORM model imported

See alembic/README.md.
"""

import os
from logging.config import fileConfig

import remitx_api.models.orm  # noqa: F401 — registers every model on Base
from alembic import context
from remitx_api.config import Config
from remitx_api.extensions import Base
from sqlalchemy import engine_from_config, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Arbitrary but fixed: every migrator must agree on it for the lock to work.
MIGRATION_LOCK_KEY = 8675309


def get_url() -> str:
    """Prefer an explicit -x url=..., otherwise the application config.

    Refuses to fall back to ``Config``'s SQLite default. That default exists so
    the API can boot without Postgres, but for migrations it is a trap: with
    DATABASE_URL unset, ``alembic upgrade head`` would create the schema in a
    local SQLite file, print "Running upgrade", and exit 0 — and ``alembic
    check`` would then agree, having compared the ORM against the wrong
    database entirely.
    """
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override

    if not os.getenv("DATABASE_URL"):
        raise RuntimeError(
            "DATABASE_URL is not set, and Alembic will not fall back to the "
            "SQLite default. Set it in the repo-root .env, export it, or pass "
            "-x url=... explicitly."
        )
    return Config.DATABASE_URL


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or manual apply."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if connection.dialect.name == "postgresql":
            # Serialises concurrent migrators — a deploy and a developer laptop
            # both running upgrade. Transaction-scoped, so it releases itself
            # on commit or rollback.
            connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": MIGRATION_LOCK_KEY},
            )

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
