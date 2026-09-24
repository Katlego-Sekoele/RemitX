"""The wake is a side effect of enqueueing, not part of it.

Two properties matter and are easy to lose:

1. The message reaches Redis *before* anything is pinged, and a publish that
   fails pings nothing at all. The wake must never be able to make a caller
   believe a message was queued.
2. The ping does not run on the request path. A cold Render instance answers
   502 immediately, but a genuinely unreachable one costs the full timeout,
   and that used to be added to every POST.
"""

from concurrent.futures import Future
from unittest.mock import MagicMock

import pytest
from remitx_api.services import queue_service


@pytest.fixture
def drain():
    """Block until every queued ping has run.

    The executor is module-level and exactly one thread wide, so a no-op
    submitted now is guaranteed to run after everything already queued. That
    makes it a barrier, and avoids both sleeping and reaching for the future
    that ``enqueue_integration_message`` deliberately does not return.
    """

    def _drain():
        queue_service._wake_executor.submit(lambda: None).result(timeout=5)

    return _drain


@pytest.fixture(autouse=True)
def _idle_wake_state(monkeypatch, drain):
    """Start every test with an idle wake.

    Both halves matter. A ping still running from an earlier test would keep
    appending to a list that test still asserts on - and would outlive the
    monkeypatch that stubbed urlopen, turning into a real network call. And a
    test that leaves the flag set would mute the next one, because wakes
    collapse.
    """
    drain()
    monkeypatch.setattr(queue_service, "_wake_in_flight", False)


@pytest.fixture
def published(monkeypatch):
    """Capture publishes without a broker. CI has no Redis."""
    calls = []
    monkeypatch.setattr(
        queue_service.producer,
        "send_task",
        lambda name, args, queue: calls.append((name, args, queue)),
    )
    return calls


@pytest.fixture
def pinged(monkeypatch):
    """Capture pings, recording what had been published by the time each ran."""
    opened = []

    def record(url, timeout):
        opened.append((url, timeout))

    monkeypatch.setattr(queue_service, "_http_get", record)
    return opened


def test_wake_skipped_when_url_unset(monkeypatch, published, pinged):
    monkeypatch.delenv("WORKER_WAKE_URL", raising=False)

    queue_service.enqueue_integration_message("msg-1")

    assert published
    assert pinged == []


def test_wake_runs_in_the_background_after_a_successful_publish(
    monkeypatch, published, pinged, drain
):
    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")

    queue_service.enqueue_integration_message("msg-1")
    drain()

    assert published == [
        (queue_service.PROCESS_INTEGRATION_MESSAGE, ["msg-1"], "settlement")
    ]
    assert pinged == [
        ("https://worker.example/health", queue_service.WAKE_TIMEOUT_SECONDS)
    ]


def test_a_failed_publish_pings_nothing(monkeypatch, pinged):
    """The task is not on Redis, so there is nothing for a worker to wake to.

    Waking here would also imply the enqueue half-succeeded; it did not, and
    the exception is what tells the caller so.
    """
    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")
    monkeypatch.setattr(
        queue_service.producer,
        "send_task",
        MagicMock(side_effect=OSError("redis unreachable")),
    )

    with pytest.raises(OSError):
        queue_service.enqueue_integration_message("msg-1")

    assert pinged == []


def test_wake_error_does_not_fail_enqueue(monkeypatch, published, drain):
    """A 502 from a booting instance is the normal case, not a failure."""
    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")
    monkeypatch.setattr(
        queue_service,
        "_http_get",
        MagicMock(side_effect=queue_service.httpx.TimeoutException("cold start")),
    )

    queue_service.enqueue_integration_message("msg-1")  # must not raise
    drain()

    assert published  # and the message is still on Redis


def test_enqueue_does_not_wait_for_the_ping(monkeypatch, published):
    """The whole point: a slow ping must not become request latency.

    ``release`` is set only after the enqueue returns, so an implementation
    that pings inline has nothing to unblock it and eats the full wait - the
    elapsed time is what separates the two, not the call succeeding.
    """
    import threading
    import time

    started = threading.Event()
    release = threading.Event()

    def blocking_ping(url, timeout):
        started.set()
        release.wait(10)

    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")
    monkeypatch.setattr(queue_service, "_http_get", blocking_ping)

    began = time.monotonic()
    queue_service.enqueue_integration_message("msg-1")
    elapsed = time.monotonic() - began
    release.set()

    assert started.wait(5), "the ping never ran"
    assert elapsed < 1, f"enqueue blocked on the ping for {elapsed:.1f}s"
    assert published  # and the message was on Redis before the ping began


def test_concurrent_wakes_collapse_into_one(monkeypatch, published):
    """One booting instance drains the queue, so one ping covers the burst."""
    import threading

    release = threading.Event()
    started = threading.Event()
    calls = []

    def slow_ping(url, timeout):
        calls.append(url)
        started.set()
        release.wait(10)

    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")
    monkeypatch.setattr(queue_service, "_http_get", slow_ping)

    first = queue_service.wake_worker()
    assert started.wait(5), "ping never started"
    skipped = [queue_service.wake_worker() for _ in range(5)]

    release.set()
    first.result(timeout=5)

    assert calls == ["https://worker.example/health"]
    assert skipped == [None] * 5


def test_a_wake_is_sent_again_once_the_previous_one_finishes(
    monkeypatch, pinged, drain
):
    """Collapsing must not latch: a later message still gets its own ping."""
    monkeypatch.setenv("WORKER_WAKE_URL", "https://worker.example/health")

    queue_service.wake_worker().result(timeout=5)
    second = queue_service.wake_worker()

    assert isinstance(second, Future)
    second.result(timeout=5)
    drain()
    assert len(pinged) == 2
