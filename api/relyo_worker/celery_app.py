import os

from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery("relyo_worker", broker=redis_url, backend=redis_url)
celery.conf.task_default_queue = "settlement"
celery.conf.task_acks_late = True
celery.autodiscover_tasks(["relyo_worker"])
