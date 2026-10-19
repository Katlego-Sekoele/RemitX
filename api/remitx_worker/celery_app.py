from celery import Celery
from celery.schedules import schedule
from celery.signals import worker_ready
from remitx_api.config import Config

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
    # Reads the stokvel contract's events into the database (R2-13).
    "stokvel-sync-events": {
        "task": "stokvel.sync_events",
        "schedule": schedule(run_every=Config.STOKVEL_SYNC_INTERVAL_SECONDS),
    },
}
celery.autodiscover_tasks(["remitx_worker"])
# The stokvel tasks (doc section 4) live in their own module.
celery.autodiscover_tasks(["remitx_worker"], related_name="stokvel_tasks")
# `stokvel.release_pool` (R3-04), apart from #232's cycle tasks.
celery.autodiscover_tasks(["remitx_worker"], related_name="stokvel_release")


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
