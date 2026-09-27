"""Throwaway Postgres databases for the `postgres` lane (see conftest.py)."""

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def throwaway_database(server_url: str) -> Iterator[str]:
    """An empty database on `server_url`'s server, dropped afterwards. Yields
    its URL."""
    name = f"remitx_test_{uuid.uuid4().hex[:8]}"
    admin = create_engine(server_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield (
            make_url(server_url)
            .set(database=name)
            .render_as_string(hide_password=False)
        )
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def migrate(database_url: str, revision: str = "head") -> None:
    """Run the API's Alembic against `database_url`, up to `revision`."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=API_ROOT,
        # No wallet: the treasury-funding migration would otherwise read a real
        # balance off the testnet.
        env={
            **os.environ,
            "DATABASE_URL": database_url,
            "PLATFORM_WALLET_ADDRESS": "",
        },
        check=True,
        capture_output=True,
    )
