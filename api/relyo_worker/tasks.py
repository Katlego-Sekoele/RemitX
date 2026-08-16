from relyo_worker.celery_app import celery


@celery.task(name="relyo_worker.tasks.ping")
def ping():
    return "pong"


@celery.task(name="relyo_worker.tasks.settle_remittance", bind=True, max_retries=3)
def settle_remittance(self, remittance_id: str):
    # Stub — XRPL settlement implemented in a later feature plan
    return {"remittance_id": remittance_id, "status": "stub"}
