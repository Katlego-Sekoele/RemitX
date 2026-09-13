import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env")

_DB_PATH = Path(__file__).resolve().parent.parent / "remitx.db"


def _split_csv(value: str) -> list:
    origins = [item.strip() for item in value.split(",") if item.strip()]
    if "*" in origins:
        # CORS is configured with allow_credentials=True, and Starlette
        # reflects the caller's Origin back when origins is "*" - which
        # would let any site make credentialed cross-origin calls.
        raise ValueError(
            "CORS_ORIGINS cannot be '*' while credentials are allowed; "
            "list the exact origins instead"
        )
    return origins


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

    # Read per-instance rather than at class-definition time: tests
    # monkeypatch the environment after import, and a class attribute would
    # freeze whatever was set when the module first loaded.
    @property
    def CLERK_SECRET_KEY(self) -> str:
        return os.getenv("CLERK_SECRET_KEY", "")

    # Written by platform_wallet/scripts/create_xprl_platform_wallet.py.
    @property
    def XRPL_ENCRYPTION_KEY(self) -> str:
        return os.getenv("XRPL_ENCRYPTION_KEY", "")

    # Public worker /health URL. Empty means do not ping after enqueue
    # (local Compose, or a future always-on worker that does not spin down).
    @property
    def WORKER_WAKE_URL(self) -> str:
        return os.getenv("WORKER_WAKE_URL", "").strip()

    @property
    def PLATFORM_WALLET_ADDRESS(self) -> str:
        return os.getenv("PLATFORM_WALLET_ADDRESS", "")

    @property
    def PLATFORM_WALLET_SEED_ENCRYPTED(self) -> str:
        return os.getenv("PLATFORM_WALLET_SEED_ENCRYPTED", "")

    # exchangerate-api.com key, used by services/exchange_rate_provider.py.
    @property
    def EXCHANGE_RATE_API_KEY(self) -> str:
        return os.getenv("EXCHANGE_RATE_API_KEY", "")


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    DATABASE_URL = "sqlite:///:memory:"
    CREATE_ALL = True

    # Verification is always mocked in tests; this only has to be non-empty
    # so the "not configured" guard in auth/clerk.py does not trip.
    CLERK_SECRET_KEY = "sk_test_fake"
