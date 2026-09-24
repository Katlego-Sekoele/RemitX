import os
from decimal import Decimal
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

    # XRPL testnet + UCTUSD issued-currency settings, shared with
    # platform_wallet/scripts/create_xprl_platform_wallet.py (same env vars,
    # same defaults) — read here too so remitx_worker/xrpl_service.py doesn't
    # duplicate the os.getenv parsing.
    @property
    def XRPL_TESTNET_URL(self) -> str:
        return os.getenv("XRPL_TESTNET_URL", "https://s.altnet.rippletest.net:51234/")

    @property
    def UCTUSD_ISSUER(self) -> str:
        return os.getenv("UCTUSD_ISSUER", "rELez4x4Zqv3KYqboYVfrYPF8521Ycbxa5")

    @property
    def UCTUSD_CURRENCY_CODE_HEX(self) -> str:
        return os.getenv(
            "UCTUSD_CURRENCY_CODE_HEX", "5543545553440000000000000000000000000000"
        )

    # The on-chain currency code UCTUSD_CURRENCY_CODE_HEX encodes, plain text.
    @property
    def UCTUSD_CURRENCY_CODE(self) -> str:
        return os.getenv("UCTUSD_CURRENCY_CODE", "UCTUSD")

    # RemitX's own internal ledger currency code (models/orm/account.py's
    # CURRENCY_TOKEN) — separate from UCTUSD_CURRENCY_CODE above, which
    # describes the real on-chain code. Kept as its own setting so the two
    # can vary independently.
    @property
    def UCTUSD_TOKEN_NAME(self) -> str:
        return os.getenv("UCTUSD_TOKEN_NAME", "uctusd")

    # Label of the platform account row representing the issuer (seeded by
    # scripts/seed_platform_accounts.py, looked up by
    # services/remittance_service.py) — both read this same env var so the
    # seeded label and the lookup can't drift apart.
    @property
    def UCTUSD_ISSUER_LABEL(self) -> str:
        return os.getenv("UCTUSD_ISSUER_LABEL", "UCTUSD Issuer (Exchange)")

    # exchangerate-api.com key, used by services/exchange_rate_provider.py.
    @property
    def EXCHANGE_RATE_API_KEY(self) -> str:
        return os.getenv("EXCHANGE_RATE_API_KEY", "")

    # --- Quote generation (services/quote_service.py, exchange_rate_service.py) ---
    # Decided fee model — Transaction_Flow_Context.md §5. FIXED_FEE_ZAR is
    # denominated in ZAR and converted into the sender's own currency at
    # quote time when it isn't ZAR (see services/quote_service.py).
    RATE_FIXING_INTERVAL_HOURS = int(os.getenv("RATE_FIXING_INTERVAL_HOURS", "1"))
    MAX_RATE_STALENESS_HOURS = int(os.getenv("MAX_RATE_STALENESS_HOURS", "26"))
    QUOTE_TTL_MINUTES = int(os.getenv("QUOTE_TTL_MINUTES", "15"))
    FIXED_FEE_ZAR = Decimal(os.getenv("FIXED_FEE_ZAR", "15"))
    PERCENTAGE_FEE_RATE = Decimal(os.getenv("PERCENTAGE_FEE_RATE", "0.005"))
    FX_MARGIN_RATE = Decimal(os.getenv("FX_MARGIN_RATE", "0.01"))
    CASH_OUT_FEE_RATE = Decimal(os.getenv("CASH_OUT_FEE_RATE", "0.0075"))
    # Floor on the cash-out fee — every withdrawal has a fee leg and amounts
    # must be positive, so this must stay >= 0.01 (services/withdrawal_service.py).
    MIN_CASH_OUT_FEE = Decimal(os.getenv("MIN_CASH_OUT_FEE", "0.01"))
    DAILY_LIMIT_ZAR_UNVERIFIED = Decimal(os.getenv("DAILY_LIMIT_ZAR_UNVERIFIED", "0"))
    MONTHLY_LIMIT_ZAR_UNVERIFIED = Decimal(
        os.getenv("MONTHLY_LIMIT_ZAR_UNVERIFIED", "0")
    )
    DAILY_LIMIT_ZAR = Decimal(os.getenv("DAILY_LIMIT_ZAR", "3000"))
    MONTHLY_LIMIT_ZAR = Decimal(os.getenv("MONTHLY_LIMIT_ZAR", "25000"))


class TestConfig(Config):
    TESTING = True
    DEBUG = False
    DATABASE_URL = "sqlite:///:memory:"
    CREATE_ALL = True

    # Verification is always mocked in tests; this only has to be non-empty
    # so the "not configured" guard in auth/clerk.py does not trip.
    CLERK_SECRET_KEY = "sk_test_fake"
