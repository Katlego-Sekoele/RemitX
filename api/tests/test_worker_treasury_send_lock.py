"""The lock that serialises every send from the EVM Treasury Wallet.

Two sends at once would read the same pending nonce, so
`evm_service.submit_transaction` holds `treasury_send_lock` from the nonce
read until the nonce has moved on. On SQLite there is nothing to lock; the
Postgres tests (marked `postgres`) check that it really excludes.
"""

import threading
import time
from types import SimpleNamespace

import pytest
from remitx_worker import db
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def _restore_factory():
    yield
    db.configure(None)


def test_the_lock_is_a_no_op_on_sqlite():
    engine = create_engine("sqlite://")
    statements = []
    engine.connect = lambda: statements.append("connect")  # must not be called
    db.configure(sessionmaker(bind=engine))

    with db.treasury_send_lock():
        pass

    assert statements == []


def test_the_lock_is_a_no_op_for_a_factory_with_no_bind():
    db.configure(lambda: None)

    with db.treasury_send_lock():
        pass


class _FakeConnection:
    def __init__(self, fail_unlock=False):
        self.statements = []
        self.fail_unlock = fail_unlock
        self.invalidated = False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append(sql)
        if self.fail_unlock and "unlock" in sql:
            raise RuntimeError("connection dropped")

    def commit(self):
        pass

    def invalidate(self):
        self.invalidated = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_postgres(connection):
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), connect=lambda: connection
    )
    db.configure(SimpleNamespace(kw={"bind": bind}))


def test_the_lock_takes_and_releases_a_postgres_advisory_lock():
    connection = _FakeConnection()
    _fake_postgres(connection)

    with db.treasury_send_lock():
        assert connection.statements == ["SELECT pg_advisory_lock(:key)"]

    assert connection.statements[-1] == "SELECT pg_advisory_unlock(:key)"
    assert connection.invalidated is False


def test_the_lock_is_released_when_the_body_raises():
    connection = _FakeConnection()
    _fake_postgres(connection)

    with pytest.raises(ValueError), db.treasury_send_lock():
        raise ValueError("send failed")

    assert connection.statements[-1] == "SELECT pg_advisory_unlock(:key)"


def test_a_failed_unlock_closes_the_connection_rather_than_pool_it():
    """A session-level lock would outlive the connection's return to the
    pool; invalidating it ends the session, which frees the lock."""
    connection = _FakeConnection(fail_unlock=True)
    _fake_postgres(connection)

    with pytest.raises(RuntimeError, match="connection dropped"):
        with db.treasury_send_lock():
            pass

    assert connection.invalidated is True


@pytest.mark.postgres
def test_the_lock_excludes_a_second_holder(postgres_url):
    engine = create_engine(postgres_url)
    db.configure(sessionmaker(bind=engine))
    order = []
    first_holds = threading.Event()

    def first():
        with db.treasury_send_lock():
            first_holds.set()
            time.sleep(0.5)
            order.append("first released")

    def second():
        first_holds.wait()
        with db.treasury_send_lock():
            order.append("second acquired")

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert order == ["first released", "second acquired"]

    # Released for good: another session can take it straight away.
    with engine.connect() as connection:
        taken = connection.execute(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": db.TREASURY_SEND_LOCK_KEY},
        ).scalar_one()
        connection.execute(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": db.TREASURY_SEND_LOCK_KEY},
        )
    assert taken is True
    engine.dispose()
