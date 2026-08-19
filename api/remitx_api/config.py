import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

_DB_PATH = Path(__file__).resolve().parent.parent / "remitx.db"


def _split_csv(value: str) -> list:
    return [item.strip() for item in value.split(",") if item.strip()]


class Config:
    DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    PORT = int(os.getenv("PORT", "4200"))
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{_DB_PATH}",
    )
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    # Shared by the API producer and the worker consumer. Both read it
    # from here so neither package has to import the other.
    CELERY_QUEUE = os.getenv("CELERY_QUEUE", "settlement")
    CORS_ORIGINS = _split_csv(os.getenv("CORS_ORIGINS", "http://localhost:5173"))

    # Alembic owns the Postgres schema in every environment (see
    # alembic/README.md), so the app never creates tables. Only throwaway
    # test databases do.
    CREATE_ALL = False


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    DATABASE_URL = "sqlite:///:memory:"
    CREATE_ALL = True
