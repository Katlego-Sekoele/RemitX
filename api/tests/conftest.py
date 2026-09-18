import uuid

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.user import KYC_APPROVED, ROLE_ADMIN, User
from remitx_api.repositories.user_repository import UserRepository
from remitx_api.services import queue_service


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
def admin_user():
    """Like `current_user`, but for exercising admin-gated (`require_admin`) routes."""
    return User(
        id=uuid.uuid4(),
        clerk_user_id="admin_test",
        email="admin@example.com",
        first_name="Admin",
        base_reference="admin1",
        role=ROLE_ADMIN,
    )


@pytest.fixture
def admin_client(admin_user):
    """Authenticated client acting as an admin."""
    app = create_app(TestConfig)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def verified_client():
    """Authenticated client backed by a real, DB-persisted, KYC-APPROVED user
    with real ZAR/uctusd accounts.

    Unlike `client`/`admin_client`, whose override object is never written to
    the database, routes that read the caller back from the DB (quotes,
    beneficiaries) need this — `current_user`'s own docstring already flags
    that gap. Yields `(test_client, user)`.
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
            persisted.kyc_status = KYC_APPROVED
            UserRepository().save(persisted)
            user_id, base_reference = persisted.id, persisted.base_reference
        finally:
            db.close_session(token)

        # A transient stand-in, not the persisted-then-detached object above:
        # accessing an attribute on that after its session closes raises
        # DetachedInstanceError the moment a route reads e.g. `user.id`.
        user = User(
            id=user_id,
            base_reference=base_reference,
            kyc_status=KYC_APPROVED,
        )
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
