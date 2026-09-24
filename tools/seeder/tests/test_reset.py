"""Reset rebuilds a database with the API's own tooling. Run against a
database of its own, so it never disturbs the seeded one."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from remitx_seeder.reset import confirmation_phrase, rebuild, recreate_schema, reset

from .conftest import create_database, drop_database, migrate


def test_reset_refuses_without_the_exact_phrase():
    with pytest.raises(ValueError, match="reset qa"):
        reset("qa", "reset local", None, lambda event: None)
    assert confirmation_phrase("local") == "reset local"


def test_reset_rebuilds_an_empty_ready_database(monkeypatch):
    name = f"remitx_seeder_reset_{uuid.uuid4().hex[:8]}"
    url = create_database(name)
    try:
        migrate(url)
        engine = create_engine(url)
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE leftover (id int)"))
        events: list[dict] = []
        monkeypatch.setenv("DATABASE_URL", url)
        monkeypatch.setenv("ADMIN_CLERK_USER_ID", "user_reset_admin")
        monkeypatch.setenv("CLERK_SECRET_KEY", "")
        recreate_schema(url, events.append)
        rebuild(events.append)
        with engine.connect() as connection:
            tables = set(
                connection.execute(
                    text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                ).scalars()
            )
            labels = set(
                connection.execute(text("SELECT label FROM accounts")).scalars()
            )
            admins = connection.execute(
                text(
                    "SELECT count(*) FROM user_roles ur JOIN roles r USING (role_id) "
                    "WHERE r.name = 'iam_admin'"
                )
            ).scalar()
        engine.dispose()
        assert "leftover" not in tables and "users" in tables
        assert {"RemitX SA Bank Account", "RemitX XRPL Treasury Wallet"} <= labels
        assert admins == 1
    finally:
        drop_database(name)
