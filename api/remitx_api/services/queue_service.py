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
import urllib.error
import urllib.request

from celery import Celery

from remitx_api.config import Config

PROCESS_INTEGRATION_MESSAGE = "remitx_worker.tasks.process_integration_message"

logger = logging.getLogger(__name__)

producer = Celery("remitx_api", broker=Config.REDIS_URL)


def wake_worker() -> None:
    """Ping the worker so a spun-down free web service starts consuming.

    Gated by ``WORKER_WAKE_URL``. Unset or blank is a no-op so local Compose
    and a future always-on worker stay producer-only. Failures are logged and
    never raised: the task is already on Redis.
    """
    url = Config().WORKER_WAKE_URL
    if not url:
        return
    try:
        urllib.request.urlopen(url, timeout=5)
    except (urllib.error.URLError, TimeoutError, OSError):
        logger.warning("worker wake at %s failed", url, exc_info=True)


def enqueue_integration_message(message_id: str) -> None:
    producer.send_task(
        PROCESS_INTEGRATION_MESSAGE,
        args=[message_id],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()
