import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.config import TestConfig
from remitx_api.extensions import db
from remitx_api.services import queue_service


@pytest.fixture
def client():
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
