"""SQLAlchemy engine pool settings for Neon Free."""

import pytest
from remitx_api.extensions import _postgres_pool_kwargs, _uses_neon_pooler, build_engine
from sqlalchemy.pool import NullPool


def test_neon_pooler_hostnames_are_detected():
    assert _uses_neon_pooler(
        "postgresql+psycopg2://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/db"
    )
    assert not _uses_neon_pooler(
        "postgresql+psycopg2://u:p@ep-x.eu-central-1.aws.neon.tech/db"
    )


def test_neon_pooler_uses_null_pool(monkeypatch):
    """PgBouncer already pools; a second QueuePool of 5+10 is the bottleneck."""
    monkeypatch.delenv("DATABASE_POOL_SIZE", raising=False)
    url = "postgresql+psycopg2://u:p@ep-x-pooler.eu-central-1.aws.neon.tech/db"
    kwargs = _postgres_pool_kwargs(url)
    assert kwargs["poolclass"] is NullPool
    assert "pool_size" not in kwargs


def test_direct_postgres_queue_pool_defaults_are_conservative(monkeypatch):
    """Defaults leave headroom for API + two Celery children under 839."""
    monkeypatch.delenv("DATABASE_POOL_SIZE", raising=False)
    monkeypatch.delenv("DATABASE_MAX_OVERFLOW", raising=False)
    kwargs = _postgres_pool_kwargs("postgresql+psycopg2://u:p@postgres/db")
    assert kwargs["pool_size"] == 10
    assert kwargs["max_overflow"] == 20
    assert (kwargs["pool_size"] + kwargs["max_overflow"]) * 3 <= 839


def test_direct_postgres_pool_is_overridable(monkeypatch):
    monkeypatch.setenv("DATABASE_POOL_SIZE", "50")
    monkeypatch.setenv("DATABASE_MAX_OVERFLOW", "100")
    kwargs = _postgres_pool_kwargs("postgresql+psycopg2://u:p@postgres/db")
    assert kwargs["pool_size"] == 50
    assert kwargs["max_overflow"] == 100


def test_invalid_pool_size_is_refused(monkeypatch):
    monkeypatch.setenv("DATABASE_POOL_SIZE", "0")
    with pytest.raises(ValueError, match="DATABASE_POOL_SIZE"):
        _postgres_pool_kwargs("postgresql+psycopg2://u:p@postgres/db")


def test_file_sqlite_ignores_pool_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_POOL_SIZE", "50")
    engine = build_engine(f"sqlite:///{tmp_path / 't.db'}")
    assert engine.url.get_backend_name() == "sqlite"
