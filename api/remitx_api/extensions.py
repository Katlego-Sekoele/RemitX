from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

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


def _uses_neon_pooler(database_url: str) -> bool:
    """Neon’s pooled hostnames include ``-pooler`` (PgBouncer, up to 10k clients)."""
    return "-pooler." in database_url or "-pooler-" in database_url


def _postgres_pool_kwargs(database_url: str) -> dict:
    """Pool settings for Postgres, sized for Neon Free.

    Neon enforces three layers (see Neon connection-pooling docs):

    - ``max_client_conn`` (10 000): clients to PgBouncer on the pooled endpoint
    - ``default_pool_size`` (0.9 × ``max_connections``): active transactions
      PgBouncer will open to Postgres (755 when ``max_connections`` is 839)
    - ``max_connections``: direct Postgres slots (and the base for the above)

    For Free autoscaling **0.25→2 CU**, Neon fixes ``max_connections`` at 839
    via ``min(max_cu, 8×min_cu)`` — not 104. The table value 104 applies only
    to a *fixed* 0.25 CU compute.

    Pooled URLs (``-pooler`` in the host) use ``NullPool`` so SQLAlchemy does
    not put a second QueuePool (default 5+10) in front of PgBouncer. Direct
    URLs use QueuePool; defaults (10+20) leave headroom for the API plus two
    Celery children. Override with ``DATABASE_POOL_SIZE`` /
    ``DATABASE_MAX_OVERFLOW`` (the load-test profile raises these under 839).
    """
    import os

    if _uses_neon_pooler(database_url):
        return {"poolclass": NullPool, "pool_pre_ping": True}

    pool_size = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
    if pool_size < 1:
        raise ValueError("DATABASE_POOL_SIZE must be >= 1")
    if max_overflow < 0:
        raise ValueError("DATABASE_MAX_OVERFLOW must be >= 0")
    return {
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }


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
    engine = create_engine(database_url, **_postgres_pool_kwargs(database_url))
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
