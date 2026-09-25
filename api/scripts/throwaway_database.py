"""A throwaway Postgres database, for tooling that needs the schema the
migrations build rather than whatever a developer's database has drifted into.

    python scripts/throwaway_database.py create        # prints its URL
    python scripts/throwaway_database.py drop <url>

``create`` makes an empty database on the server ``DBML_DATABASE_URL`` names,
or else ``DATABASE_URL`` (read from the repo-root .env, as the API does). That
URL's role needs CREATEDB; the compose superuser and CI's ``postgres`` have it.
``drop`` refuses any database this script did not name.

``scripts/generate-dbml.sh`` is the caller: it migrates the database to head,
reads it with db2dbml and drops it.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "remitx_throwaway_"


def server_url() -> URL:
    load_dotenv(ROOT / ".env")
    raw = os.getenv("DBML_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not raw.startswith("postgresql"):
        raise SystemExit(
            "Set DBML_DATABASE_URL (or DATABASE_URL) to a Postgres server this "
            "may create a database on, e.g. the compose one: "
            "postgresql+psycopg2://remitx:remitx@localhost:5432/remitx"
        )
    return make_url(raw)


def _execute(url: URL, statement: str) -> None:
    # CREATE and DROP DATABASE refuse to run inside a transaction.
    engine = create_engine(url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with engine.connect() as connection:
            connection.execute(text(statement))
    except OperationalError as exc:
        raise SystemExit(
            f"Cannot reach Postgres at {url.render_as_string()}: {exc.orig}"
        ) from None
    finally:
        engine.dispose()


def create() -> str:
    server = server_url()
    name = PREFIX + secrets.token_hex(4)
    _execute(server, f'CREATE DATABASE "{name}"')
    return server.set(database=name).render_as_string(hide_password=False)


def drop(url: str) -> None:
    name = make_url(url).database or ""
    if not name.startswith(PREFIX):
        raise SystemExit(f"Refusing to drop {name!r}: this script did not create it")
    # FORCE ends connections a reader left open, which would block the drop.
    _execute(server_url(), f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create", help="create one and print its URL")
    drop_parser = commands.add_parser("drop", help="drop one created by `create`")
    drop_parser.add_argument("url")
    args = parser.parse_args(argv)

    if args.command == "create":
        print(create())
    else:
        drop(args.url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
