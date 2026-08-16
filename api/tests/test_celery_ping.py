import os

import pytest
from relyo_worker.celery_app import celery
from relyo_worker.tasks import ping

pytestmark = pytest.mark.skipif(
    os.getenv("SKIP_REDIS_TESTS", "1") == "1",
    reason="Redis not available",
)


def test_celery_ping_task_registered():
    assert "relyo_worker.tasks.ping" in celery.tasks


def test_ping_returns_pong():
    result = ping.apply(args=[])
    assert result.get(timeout=10) == "pong"
