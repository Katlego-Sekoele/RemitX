from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from remitx_api.db.request_db_session import (
    current_request_db_session,
    require_request_db_session,
    reset_request_db_session,
    set_request_db_session,
)
from remitx_api.db.rls import (
    adopt_row_security_role,
    register_row_security_listeners,
)


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def _set_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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
    engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
    adopt_row_security_role(engine)
    return engine


class Database:
    def __init__(self) -> None:
        self.engine = None
        self._session_factory = None

    @property
    def session(self) -> Session:
        return require_request_db_session()

    def init(self, database_url: str) -> None:
        self.engine = build_engine(database_url)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )
        register_row_security_listeners()

    def open_session(self):
        """Open a session for the current context, returning a reset token."""
        if self._session_factory is None:
            raise RuntimeError("Database is not initialized")
        return set_request_db_session(self._session_factory())

    def close_session(self, token=None) -> None:
        session = current_request_db_session()
        if session is not None:
            session.close()
        reset_request_db_session(token)

    def create_all(self) -> None:
        if self.engine is None:
            raise RuntimeError("Database is not initialized")
        Base.metadata.create_all(bind=self.engine)


db = Database()
