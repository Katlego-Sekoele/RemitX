import uuid

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.extensions import db
from remitx_api.models.orm.user import User
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
