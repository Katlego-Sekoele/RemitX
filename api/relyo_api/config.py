import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

_DB_PATH = Path(__file__).resolve().parent.parent / "relyo.db"


class Config:
    DEBUG = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    PORT = int(os.getenv("PORT", "4200"))
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{_DB_PATH}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
