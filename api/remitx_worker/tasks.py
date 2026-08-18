from remitx_worker.celery_app import celery


@celery.task(name="remitx_worker.tasks.ping")
def ping():
    return "pong"
