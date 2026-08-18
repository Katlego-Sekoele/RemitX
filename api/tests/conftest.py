import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.config import TestConfig


@pytest.fixture
def client():
    app = create_app(TestConfig)
    with TestClient(app) as test_client:
        yield test_client
