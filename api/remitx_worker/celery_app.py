from celery import Celery
from celery.schedules import schedule
from celery.signals import worker_ready
from remitx_api.config import Config
from remitx_api.log_redaction import install_log_redaction

install_log_redaction()

# Config, not os.getenv, so the worker loads the same root .env as the API.
celery = Celery(
    "remitx_worker",
    broker=Config.REDIS_URL,
    backend=Config.REDIS_URL,
)
celery.conf.task_default_queue = Config.CELERY_QUEUE
celery.conf.task_acks_late = True
celery.conf.beat_schedule = {
    "reclaim-stuck-settlements": {
        "task": "remitx_worker.tasks.reclaim_stuck_settlements",
        "schedule": schedule(run_every=Config.SETTLEMENT_RECLAIM_INTERVAL_SECONDS),
    },
}
celery.autodiscover_tasks(["remitx_worker"])


@worker_ready.connect
def _reclaim_on_ready(**_kwargs) -> None:
    from remitx_worker import db
    from remitx_worker.reclaim import reclaim_on_worker_boot

    try:
        reclaim_on_worker_boot()
    finally:
        # This runs in the pool parent, after the children have forked. Its
        # engine is its own and is never used again, so hand the connections
        # back rather than idling on them for the worker's lifetime.
        db.dispose()
