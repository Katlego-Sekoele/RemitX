"""Regression tests for per-request database session isolation.

The session used to live in a single attribute on the module-level ``db``
object. FastAPI runs sync (``def``) routes in an anyio worker thread and serves
requests concurrently, so one request would close the session another was still
writing through. Against real Postgres, 24 concurrent POSTs produced 6
successes, 18 500s ("Database session is not active"), and 15 rows.

These run against a *file-backed* SQLite database rather than the usual
in-memory one: the in-memory config uses StaticPool, which shares a single
connection across every thread, and concurrent writes through one SQLite
connection segfault the interpreter. A file database gives each thread its own
connection, which is also what Postgres does in production.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig

CONCURRENCY = 24
ENDPOINT = "/integration-messages"


@pytest.fixture
def concurrent_client(tmp_path, current_user):
    """Builds its own app (a file-backed DB, not the shared in-memory one —
    see module docstring), so it needs its own auth override too."""

    class FileDbConfig(TestConfig):
        DATABASE_URL = f"sqlite:///{tmp_path / 'concurrency.db'}"

    app = create_app(FileDbConfig)
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app) as test_client:
        yield test_client


def test_concurrent_creates_all_succeed_and_persist(concurrent_client, enqueued):
    def post(index):
        return concurrent_client.post(
            ENDPOINT,
            json={"body": f"concurrent-{index:02d}"},
        )

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        responses = list(pool.map(post, range(CONCURRENCY)))

    assert [r.status_code for r in responses] == [202] * CONCURRENCY

    stored = concurrent_client.get(ENDPOINT, params={"limit": 200}).json()
    assert len(stored) == CONCURRENCY
    assert len({m["id"] for m in stored}) == CONCURRENCY
    assert len(enqueued) == CONCURRENCY


def test_concurrent_reads_do_not_disturb_each_other(concurrent_client, enqueued):
    concurrent_client.post(ENDPOINT, json={"body": "seed"})

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        responses = list(
            pool.map(lambda _: concurrent_client.get(ENDPOINT), range(CONCURRENCY))
        )

    assert [r.status_code for r in responses] == [200] * CONCURRENCY
    assert all(len(r.json()) == 1 for r in responses)
