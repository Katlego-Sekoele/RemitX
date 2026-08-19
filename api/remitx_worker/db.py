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
