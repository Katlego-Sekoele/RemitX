from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


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
        self.engine = create_engine(database_url)
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
