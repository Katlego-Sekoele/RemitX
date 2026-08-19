"""The API and the worker agree on a task name and a queue, and nothing else.

Every other test patches the enqueue call out, so without these the two halves
could drift: a renamed task or a mismatched queue would leave messages sitting
in PENDING forever while the whole suite still passed.
"""

from remitx_api.config import Config
from remitx_api.services.queue_service import PROCESS_INTEGRATION_MESSAGE
from remitx_worker.celery_app import celery
from remitx_worker.tasks import process_integration_message


def test_producer_targets_a_task_the_worker_registers():
    assert PROCESS_INTEGRATION_MESSAGE == process_integration_message.name
    assert PROCESS_INTEGRATION_MESSAGE in celery.tasks


def test_producer_and_worker_use_the_same_queue():
    assert celery.conf.task_default_queue == Config.CELERY_QUEUE
