import pytest
from relyo_api import create_app
from relyo_api.config import TestConfig


@pytest.fixture
def client():
    app = create_app(TestConfig)
    with app.test_client() as test_client:
        yield test_client
