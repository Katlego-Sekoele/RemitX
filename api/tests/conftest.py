import os
import uuid

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.kyc_lifecycle import KYC_TIER_VERIFIED, KycStatus
from remitx_api.models.orm.user import User
from remitx_api.services import queue_service
from tests.kyc_helpers import insert_application
from tests.postgres_helpers import migrate, throwaway_database


@pytest.fixture
def current_user():
    """The caller every authenticated test acts as.

    Not persisted: no endpoint reads it back from the database yet. The first
    route that scopes data per user will need this inserted instead.
    """
    return User(
        id=uuid.uuid4(),
        clerk_user_id="user_test",
        email="test@example.com",
        first_name="Test",
        base_reference="test1",
    )


@pytest.fixture
def client(current_user):
    """Authenticated client. Token verification is bypassed, not faked —
    exercising real Clerk verification is test_clerk_verification.py's job."""
    app = create_app(TestConfig)
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def verified_client():
    """Authenticated client backed by a real, DB-persisted, KYC-verified user
    with real ZAR/uctusd accounts.

    Unlike `client`, whose override object is never written to the database,
    routes that read the caller back from the DB (quotes, beneficiaries) need
    this — `current_user`'s own docstring already flags that gap. KYC
    standing is derived from `kyc_applications`, not stored on `User` — see
    models/orm/user.py — so verification is granted by inserting an approved
    application row, not by setting an attribute. Yields `(test_client,
    user)`.
    """
    app = create_app(TestConfig)
    with TestClient(app) as test_client:
        token = db.open_session()
        try:
            persisted = UserController().ensure_provisioned(
                "user_verified_test",
                lambda: "verified@example.com",
                lambda: "Verified",
            )
            insert_application(
                persisted.id,
                status=KycStatus.APPROVED,
                tier_granted=KYC_TIER_VERIFIED,
            )
            user_id, base_reference = persisted.id, persisted.base_reference
        finally:
            db.close_session(token)

        # A transient stand-in, not the persisted-then-detached object above:
        # accessing an attribute on that after its session closes raises
        # DetachedInstanceError the moment a route reads e.g. `user.id`.
        user = User(id=user_id, base_reference=base_reference)
        app.dependency_overrides[get_current_user] = lambda: user
        yield test_client, user


@pytest.fixture
def anonymous_client():
    """Client with no auth override, so the real dependency runs and rejects."""
    app = create_app(TestConfig)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def app_context():
    """Open a DB session outside a request, for repository/model tests.

    The app's session middleware only runs per-request, so anything touching
    db.session directly has to open one itself.
    """
    app = create_app(TestConfig)
    with TestClient(app):
        token = db.open_session()
        try:
            yield
        finally:
            db.close_session(token)


@pytest.fixture
def enqueued(monkeypatch):
    """Capture enqueue calls instead of publishing. CI has no Redis."""
    calls = []
    monkeypatch.setattr(
        queue_service,
        "enqueue_integration_message",
        calls.append,
    )
    return calls


# --- The Postgres lane -------------------------------------------------------
#
# Some guarantees only exist on Postgres: SQLite ignores `SELECT ... FOR
# UPDATE`, and has no row-level security, triggers or partial indexes. Tests
# marked `postgres` run against a real server named by TEST_DATABASE_URL (CI's
# Postgres service; locally any Postgres you can create databases on) and skip
# when it is unset, so the default lane stays fast and needs nothing running.


@pytest.fixture(scope="session")
def postgres_server_url():
    server_url = os.environ.get("TEST_DATABASE_URL")
    if not server_url:
        pytest.skip("TEST_DATABASE_URL is not set")
    return server_url


@pytest.fixture(scope="session")
def postgres_url(postgres_server_url):
    """A throwaway database on that server, migrated with the API's Alembic
    so it has the real schema, and dropped at the end."""
    with throwaway_database(postgres_server_url) as url:
        migrate(url)
        yield url


@pytest.fixture
def empty_postgres_url(postgres_server_url):
    """A database of the test's own, not migrated yet: for tests that step
    through migrations with `tests.postgres_helpers.migrate`."""
    with throwaway_database(postgres_server_url) as url:
        yield url


@pytest.fixture
def postgres_app(postgres_url):
    """The app on that database, running as the row-security role like
    production. Migrations own the schema, so nothing is created here."""

    class PostgresTestConfig(TestConfig):
        DATABASE_URL = postgres_url
        CREATE_ALL = False

    app = create_app(PostgresTestConfig)
    with TestClient(app):
        yield app
    db.engine.dispose()
