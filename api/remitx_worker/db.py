"""Database access for Celery tasks.

The API's ``db`` singleton holds a single request-scoped session installed by
HTTP middleware, which is not valid under Celery's prefork model. The worker
therefore owns its own engine and session factory, built lazily on first use so
tests can substitute one.
"""

from contextlib import contextmanager

from celery.signals import worker_process_init
from remitx_api.config import Config
from remitx_api.extensions import build_engine
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

_session_factory = None

# The Postgres advisory lock every send from the EVM Treasury Wallet holds
# (`treasury_send_lock`). Any constant works as long as every sender uses the
# same one; these eight bytes spell "REMITXTR".
TREASURY_SEND_LOCK_KEY = 0x52454D4954585452


@worker_process_init.connect
def _reset_engine_after_fork(**_kwargs) -> None:
    """Never let a forked child inherit the parent's connections.

    Nothing builds the engine before fork today, so this is currently a no-op
    — but that safety is incidental. Any future pre-fork call (a warm-up hook,
    a health probe) would fork live sockets into every child and corrupt them
    intermittently. Cheaper to make the guarantee explicit than to debug that.
    """
    global _session_factory
    _session_factory = None


def configure(session_factory) -> None:
    """Replace the session factory. Used by tests to point at a scratch DB."""
    global _session_factory
    _session_factory = session_factory


def dispose() -> None:
    """Return pooled connections and drop the factory; the next use rebuilds.

    The startup reclaim runs in the pool parent, which then never touches the
    database again. Without this it holds an idle Postgres pool for the life
    of the worker - connections Neon counts and memory the 512 MB instance
    cannot spare.
    """
    global _session_factory
    if _session_factory is None:
        return
    # getattr: tests can configure() any session-returning callable, not
    # necessarily a sessionmaker with a bind to release.
    bind = getattr(_session_factory, "kw", {}).get("bind")
    if bind is not None:
        bind.dispose()
    _session_factory = None


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=build_engine(Config.DATABASE_URL),
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


@contextmanager
def session_scope():
    """Session per task: commit on success, roll back on failure, always close."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def treasury_send_lock():
    """Hold the lock that lets one Treasury transaction be built and sent at a time.

    Every send from the EVM Treasury Wallet reads the wallet's pending nonce,
    so two sends at once can take the same nonce and one replaces or is
    rejected in favour of the other. `evm_service.submit_transaction` holds
    this from the nonce read until the send has been accepted, which
    serialises the burn, the contribution tasks and `finalise` across every
    worker process.

    A transaction-level `pg_advisory_xact_lock`, taken in a transaction of
    its own on a connection of its own, so the caller can still commit its
    own sessions while holding it. The transaction stays open for the whole
    send and the lock goes when it ends, on commit, on rollback when the
    body raises, or when the connection drops. There is no unlock statement
    to land on the wrong server connection: Neon's `-pooler` host
    (PgBouncer, transaction mode) can move a client between server
    connections between transactions, never within one. The same reason
    `remitx_api.db.rls` uses `SET LOCAL ROLE`.

    Waits for as long as another sender holds it. On SQLite (tests) there is
    nothing to lock and it does nothing.
    """
    bind = getattr(get_session_factory(), "kw", {}).get("bind")
    if bind is None or bind.dialect.name != "postgresql":
        yield
        return
    with bind.connect() as connection, connection.begin():
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": TREASURY_SEND_LOCK_KEY}
        )
        yield
