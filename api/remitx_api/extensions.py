from contextvars import ContextVar
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    """Create an engine, pinning in-memory SQLite to a single connection.

    Without StaticPool every connection to an in-memory SQLite database opens
    its own empty copy, so tables created during setup are invisible to the
    next caller.

    ``pool_pre_ping`` matters against Neon, which autosuspends idle computes
    and drops connections server-side; without it the first query after an idle
    period fails with "server closed the connection unexpectedly".
    """
    if database_url.startswith("sqlite") and (
        ":memory:" in database_url or database_url == "sqlite://"
    ):
        return create_engine(
            database_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    if database_url.startswith("sqlite"):
        return create_engine(database_url)
    return create_engine(database_url, pool_pre_ping=True, pool_recycle=300)


# Per-request, not per-process. FastAPI runs sync (`def`) routes in an anyio
# worker thread and serves requests concurrently, so a single shared session
# attribute lets one request close the session another is still writing
# through — losing writes and raising "session is not active" under load.
# ContextVars are copied into anyio worker threads, so sync routes see the
# session opened for their own request and nothing else.
_session_cv: ContextVar[Optional[Session]] = ContextVar(
    "remitx_db_session",
    default=None,
)


class Database:
    def __init__(self) -> None:
        self.engine = None
        self._session_factory = None

    @property
    def session(self) -> Session:
        session = _session_cv.get()
        if session is None:
            raise RuntimeError("Database session is not active")
        return session

    def init(self, database_url: str) -> None:
        self.engine = build_engine(database_url)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )

    def open_session(self):
        """Open a session for the current context, returning a reset token."""
        if self._session_factory is None:
            raise RuntimeError("Database is not initialized")
        return _session_cv.set(self._session_factory())

    def close_session(self, token=None) -> None:
        session = _session_cv.get()
        if session is not None:
            session.close()
        if token is None:
            _session_cv.set(None)
        else:
            _session_cv.reset(token)

    def create_all(self) -> None:
        if self.engine is None:
            raise RuntimeError("Database is not initialized")
        Base.metadata.create_all(bind=self.engine)


db = Database()
