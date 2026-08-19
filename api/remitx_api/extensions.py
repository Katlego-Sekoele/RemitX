from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def build_engine(database_url: str):
    """Create an engine, pinning in-memory SQLite to a single connection.

    Without StaticPool every connection to ``sqlite:///:memory:`` opens its own
    empty database, so tables created during setup are invisible to the next
    caller.
    """
    if database_url == "sqlite:///:memory:":
        return create_engine(
            database_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_engine(database_url)


class Database:
    def __init__(self) -> None:
        self.engine = None
        self._session_factory = None
        self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Database session is not active")
        return self._session

    def init(self, database_url: str) -> None:
        self.engine = build_engine(database_url)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )

    def open_session(self) -> None:
        if self._session_factory is None:
            raise RuntimeError("Database is not initialized")
        self._session = self._session_factory()

    def close_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def create_all(self) -> None:
        if self.engine is None:
            raise RuntimeError("Database is not initialized")
        Base.metadata.create_all(bind=self.engine)


db = Database()
