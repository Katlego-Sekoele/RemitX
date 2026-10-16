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
    """Records statements and how the lock's transaction ended."""

    def __init__(self):
        self.statements = []
        self.ended = None

    def execute(self, statement, params=None):
        self.statements.append(str(statement))

    def begin(self):
        connection = self

        class _Transaction:
            def __enter__(self):
                connection.statements.append("BEGIN")
                return self

            def __exit__(self, exc_type, *_exc):
                connection.ended = "rollback" if exc_type else "commit"
                return False

        return _Transaction()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_postgres(connection):
    bind = SimpleNamespace(
        dialect=SimpleNamespace(name="postgresql"), connect=lambda: connection
    )
    db.configure(SimpleNamespace(kw={"bind": bind}))


def test_the_lock_is_a_transaction_level_lock_with_no_unlock():
    """Through Neon's transaction pooler an unlock in a later statement can
    reach a different server connection. A transaction-level lock has no
    unlock: it goes when its transaction ends."""
    connection = _FakeConnection()
    _fake_postgres(connection)

    with db.treasury_send_lock():
        assert connection.statements == [
            "BEGIN",
            "SELECT pg_advisory_xact_lock(:key)",
        ]
        assert connection.ended is None

    assert connection.ended == "commit"
    assert not any("unlock" in sql for sql in connection.statements)


def test_the_lock_transaction_rolls_back_when_the_body_raises():
    connection = _FakeConnection()
    _fake_postgres(connection)

    with pytest.raises(ValueError), db.treasury_send_lock():
        raise ValueError("send failed")

    assert connection.ended == "rollback"


def _advisory_locks_held(engine) -> int:
    """How many backends hold the Treasury send lock right now. A bigint
    advisory key is stored split: high 32 bits in `classid`, low in `objid`."""
    key = db.TREASURY_SEND_LOCK_KEY
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'"
                " AND granted AND classid = :high AND objid = :low"
                " AND objsubid = 1"
            ),
            {"high": key >> 32, "low": key & 0xFFFFFFFF},
        ).scalar_one()


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


@pytest.mark.postgres
def test_the_lock_is_held_only_inside_the_block(postgres_url):
    """Held while the block runs, and gone after it on every backend: no
    unlock was needed, so none can be lost."""
    engine = create_engine(postgres_url)
    db.configure(sessionmaker(bind=engine))

    with db.treasury_send_lock():
        assert _advisory_locks_held(engine) == 1

    assert _advisory_locks_held(engine) == 0
    engine.dispose()


@pytest.mark.postgres
def test_the_lock_is_released_when_the_send_raises(postgres_url):
    engine = create_engine(postgres_url)
    db.configure(sessionmaker(bind=engine))

    with pytest.raises(RuntimeError, match="node refused"):
        with db.treasury_send_lock():
            raise RuntimeError("node refused")

    assert _advisory_locks_held(engine) == 0
    with engine.connect() as connection, connection.begin():
        taken = connection.execute(
            text("SELECT pg_try_advisory_xact_lock(:key)"),
            {"key": db.TREASURY_SEND_LOCK_KEY},
        ).scalar_one()
    assert taken is True
    engine.dispose()
