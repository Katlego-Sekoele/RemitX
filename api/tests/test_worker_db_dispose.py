"""The startup reclaim hands its connections back instead of idling on them.

``reclaim_pending_messages`` runs in the pool parent, after the children have
forked, and the parent never touches the database again. Its engine would
otherwise hold an idle Postgres pool for the life of the worker - connections
Neon counts against the project and memory a 512 MB instance cannot spare.
"""

from remitx_worker import celery_app, db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_dispose_releases_the_engine_and_clears_the_factory():
    engine = create_engine("sqlite://")
    disposed = []
    engine.dispose = lambda *a, **k: disposed.append(True)
    db.configure(sessionmaker(bind=engine))

    db.dispose()

    assert disposed == [True]
    assert db.get_session_factory() is not None  # rebuilt lazily


def test_dispose_without_a_factory_is_a_no_op():
    db.configure(None)

    db.dispose()  # must not raise


def test_dispose_tolerates_a_factory_with_no_bind():
    """Tests may configure any session-returning callable, not a sessionmaker."""
    db.configure(lambda: None)

    db.dispose()

    assert db._session_factory is None


def test_reclaim_disposes_even_when_it_fails(monkeypatch):
    """A reclaim that raises must not leak the parent's pool."""
    disposed = []
    monkeypatch.setattr(db, "dispose", lambda: disposed.append(True))
    monkeypatch.setattr(
        "remitx_worker.reclaim.reclaim_on_worker_boot",
        lambda: (_ for _ in ()).throw(RuntimeError("database down")),
    )

    try:
        celery_app._reclaim_on_ready()
    except RuntimeError:
        pass

    assert disposed == [True]
