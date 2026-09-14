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
    # Celery's own default is os.cpu_count(), which is the wrong number on a
    # memory-capped host: Render reports the underlying box's 8 cores while
    # the free instance is capped at 512 MB. Nine processes that each import
    # remitx_api (FastAPI + SQLAlchemy + boto3 + clerk + xrpl) measured
    # ~925 MB, so the worker was OOM-killed between "mingle" and "ready" and
    # consumed nothing. Concurrency here is bounded by memory, not cores.
    CELERY_CONCURRENCY = int(os.getenv("CELERY_CONCURRENCY", "2"))
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

    # --- Object storage (Neon Object Storage in the cloud, MinIO locally) ---
    #
    # KYC documents are bytes, and bytes do not belong in Postgres: a database
    # dump taken to debug something should not contain a stranger's passport.
    # The API never handles the upload itself - it signs a URL and the browser
    # PUTs straight to the bucket.

    @property
    def OBJECT_STORAGE_ENDPOINT_URL(self) -> str:
        """S3 endpoint the API itself talks to (container-internal locally)."""
        return os.getenv("OBJECT_STORAGE_ENDPOINT_URL", "").strip()

    @property
    def OBJECT_STORAGE_PUBLIC_ENDPOINT_URL(self) -> str:
        """Endpoint the *browser* uses, which presigned URLs must be signed for.

        The host is part of the SigV4 signature, so a URL signed for
        ``http://minio:9000`` fails when the browser resolves
        ``http://localhost:9000``. In the cloud both are the same host and
        this stays unset.
        """
        return (
            os.getenv("OBJECT_STORAGE_PUBLIC_ENDPOINT_URL", "").strip()
            or self.OBJECT_STORAGE_ENDPOINT_URL
        )

    @property
    def OBJECT_STORAGE_BUCKET(self) -> str:
        return os.getenv("OBJECT_STORAGE_BUCKET", "kyc-documents").strip()

    @property
    def OBJECT_STORAGE_REGION(self) -> str:
        # Neon Object Storage ignores the region but SigV4 requires one in the
        # credential scope, so it has to be some agreed string.
        return os.getenv("OBJECT_STORAGE_REGION", "auto").strip()

    @property
    def OBJECT_STORAGE_ACCESS_KEY_ID(self) -> str:
        return os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID", "")

    @property
    def OBJECT_STORAGE_SECRET_ACCESS_KEY(self) -> str:
        return os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY", "")

    @property
    def PLATFORM_WALLET_ADDRESS(self) -> str:
        return os.getenv("PLATFORM_WALLET_ADDRESS", "")

    @property
    def PLATFORM_WALLET_SEED_ENCRYPTED(self) -> str:
        return os.getenv("PLATFORM_WALLET_SEED_ENCRYPTED", "")


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    DATABASE_URL = "sqlite:///:memory:"
    CREATE_ALL = True

    # Verification is always mocked in tests; this only has to be non-empty
    # so the "not configured" guard in auth/clerk.py does not trip.
    CLERK_SECRET_KEY = "sk_test_fake"
