import logging
import uuid

from remitx_api.models.orm.integration_message import (
    STATUS_PENDING,
    STATUS_PROCESSED,
    IntegrationMessage,
    utcnow,
)
from sqlalchemy import update

from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope

logger = logging.getLogger(__name__)


@celery.task(name="remitx_worker.tasks.ping")
def ping():
    return "pong"


@celery.task(name="remitx_worker.tasks.process_integration_message")
def process_integration_message(message_id: str) -> str:
    """Move an integration message from PENDING to PROCESSED.

    THROWAWAY: part of the manual end-to-end integration test.

    The ``status == PENDING`` predicate is what makes this safe to run twice.
    The Celery app sets ``acks_late``, so redelivery after a worker crash is
    expected rather than exceptional: a duplicate simply matches no rows and
    the original ``processed_at`` is left untouched.
    """
    with session_scope() as session:
        result = session.execute(
            update(IntegrationMessage)
            .where(
                IntegrationMessage.id == uuid.UUID(message_id),
                IntegrationMessage.status == STATUS_PENDING,
            )
            .values(status=STATUS_PROCESSED, processed_at=utcnow())
        )
        updated = result.rowcount

    if updated == 0:
        logger.info(
            "integration message %s already processed or unknown; skipping",
            message_id,
        )
        return "skipped"

    logger.info("integration message %s processed", message_id)
    return "processed"
