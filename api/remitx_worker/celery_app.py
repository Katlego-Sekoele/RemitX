from celery import Celery
from remitx_api.config import Config

# Config, not os.getenv, so the worker loads the same root .env as the API.
celery = Celery(
    "remitx_worker",
    broker=Config.REDIS_URL,
    backend=Config.REDIS_URL,
)
celery.conf.task_default_queue = Config.CELERY_QUEUE
celery.conf.task_acks_late = True
celery.autodiscover_tasks(["remitx_worker"])
