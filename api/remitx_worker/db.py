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
from sqlalchemy.orm import sessionmaker

_session_factory = None


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
