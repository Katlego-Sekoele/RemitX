"""Celery producer for the API.

The API owns a producer of its own rather than importing the worker's Celery
app. Two reasons:

1. It keeps the dependency one-directional. ``remitx_worker`` imports
   ``remitx_api`` for config and ORM models; if the API imported the worker
   back, the two form a cycle that only shows up at runtime.
2. Producing and consuming are genuinely different roles. The API never needs
   to know what a task does, only its name and which queue it goes on.
"""

from celery import Celery

from remitx_api.config import Config

PROCESS_INTEGRATION_MESSAGE = "remitx_worker.tasks.process_integration_message"

producer = Celery("remitx_api", broker=Config.REDIS_URL)


def enqueue_integration_message(message_id: str) -> None:
    producer.send_task(
        PROCESS_INTEGRATION_MESSAGE,
        args=[message_id],
        queue=Config.CELERY_QUEUE,
    )
