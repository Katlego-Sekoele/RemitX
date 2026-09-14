"""Celery producer for the API.

The API owns a producer of its own rather than importing the worker's Celery
app. Two reasons:

1. It keeps the dependency one-directional. ``remitx_worker`` imports
   ``remitx_api`` for config and ORM models; if the API imported the worker
   back, the two form a cycle that only shows up at runtime.
2. Producing and consuming are genuinely different roles. The API never needs
   to know what a task does, only its name and which queue it goes on.
"""

import logging
import threading
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor

from celery import Celery

from remitx_api.config import Config

PROCESS_INTEGRATION_MESSAGE = "remitx_worker.tasks.process_integration_message"

# Short on purpose, and not a deadline for the worker to finish booting. The
# ping exists to make Render's router start a spun-down instance, and that
# happens when the request arrives, not when it answers - a cold instance
# usually replies 502 long before it is ready. Nothing reads the response, so
# a longer wait would buy nothing and would only lengthen the join at
# interpreter exit.
WAKE_TIMEOUT_SECONDS = 5

logger = logging.getLogger(__name__)

producer = Celery("remitx_api", broker=Config.REDIS_URL)

# One thread, never more. A wake is a side effect of enqueueing rather than
# part of it, and the request that triggered it has already been answered.
# Threads are created on first submit, so an API with no WORKER_WAKE_URL
# never starts one.
_wake_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="worker-wake")
_wake_lock = threading.Lock()
_wake_in_flight = False


def _ping(url: str) -> None:
    global _wake_in_flight
    try:
        urllib.request.urlopen(url, timeout=WAKE_TIMEOUT_SECONDS)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Never the enqueue's problem: the task is already on Redis, and the
        # worker re-enqueues leftover PENDING rows when it does boot. A 502
        # here is the ordinary answer from an instance that is still starting.
        #
        # One line, no traceback: every frame of it is urllib internals, and
        # this fires on every cold start. The exception already names the
        # cause, and a wall of stack for the expected case buries the
        # unexpected one.
        logger.warning("worker wake at %s failed: %s", url, exc)
    finally:
        with _wake_lock:
            _wake_in_flight = False


def wake_worker() -> Future | None:
    """Ping the worker off the request path so a spun-down instance starts.

    Gated by ``WORKER_WAKE_URL``. Unset or blank is a no-op so local Compose
    and a future always-on worker stay producer-only.

    Wakes collapse: while one ping is outstanding, another is not sent. A
    worker booting because of an earlier ping drains the whole queue when it
    comes up, so a second ping for a message enqueued in the meantime would
    wake nothing that is not already waking. Without this, a burst of
    enqueues would queue a burst of pings behind a single thread and each
    would still be answered by the same booting instance.

    Returns the pending ping, or ``None`` when there is nothing to do.
    Callers are free to ignore it; tests use it to wait rather than sleep.
    """
    url = Config().WORKER_WAKE_URL
    if not url:
        return None
    global _wake_in_flight
    with _wake_lock:
        if _wake_in_flight:
            return None
        _wake_in_flight = True
    return _wake_executor.submit(_ping, url)


def enqueue_integration_message(message_id: str) -> None:
    """Put the task on Redis, then wake the worker - never the other way round.

    ``send_task`` is synchronous and raises if the broker cannot be reached
    (Celery retries the publish first), so returning from here means the
    message is on Redis and a caller that gets an exception knows it is not.
    The wake is deliberately outside that guarantee: it runs in the
    background and only logs on failure, because a task already on Redis is
    not lost by a ping that did not land.
    """
    producer.send_task(
        PROCESS_INTEGRATION_MESSAGE,
        args=[message_id],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()
