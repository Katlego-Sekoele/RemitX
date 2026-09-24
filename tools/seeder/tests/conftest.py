"""A throwaway, migrated Postgres for the seeder's tests.

The seeder drives the real backend, so its tests need the real schema: row
security, triggers and partial indexes included, which SQLite cannot give.
`SEEDER_TEST_DATABASE_URL` names a server (CI's Postgres service; locally any
Postgres you can create databases on). Each test session creates its own
database there, migrates it with the API's Alembic, and drops it at the end.

`DATABASE_URL` must be set before anything imports `remitx_api` (its Config
reads it at import), so this happens in `pytest_configure`.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from remitx_seeder.settings import REPO_ROOT

SERVER_URL = os.environ.get(
    "SEEDER_TEST_DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres",
)
DATABASE_NAME = f"remitx_seeder_test_{uuid.uuid4().hex[:8]}"


def _admin_engine():
    return create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")


def create_database(name: str) -> str:
    engine = _admin_engine()
    with engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    return make_url(SERVER_URL).set(database=name).render_as_string(hide_password=False)


def drop_database(name: str) -> None:
    engine = _admin_engine()
    with engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    engine.dispose()


def migrate(database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT / "api",
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
        capture_output=True,
    )


def pytest_configure(config) -> None:
    url = create_database(DATABASE_NAME)
    os.environ["DATABASE_URL"] = url
    os.environ["CLERK_SECRET_KEY"] = ""
    migrate(url)
    config._seeder_database = DATABASE_NAME


def pytest_unconfigure(config) -> None:
    name = getattr(config, "_seeder_database", None)
    if name:
        from remitx_api.extensions import db

        if db.engine is not None:
            db.engine.dispose()
        from remitx_worker import db as worker_db

        worker_db.dispose()
        drop_database(name)


@pytest.fixture(scope="session")
def database():
    """The migrated test database: the migrations create the platform
    accounts, which is all a run needs, the same as after a Reset."""
    from remitx_api.config import Config
    from remitx_api.extensions import db

    if db.engine is None:
        db.init(Config.DATABASE_URL)
    return db
