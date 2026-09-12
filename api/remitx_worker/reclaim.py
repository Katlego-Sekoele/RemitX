"""Re-enqueue PENDING rows after a broker wipe.

Free Render Key Value is in-memory and may restart empty. Postgres is the
source of truth; this walks leftover PENDING messages back onto the queue.
``process_integration_message`` is idempotent, so a message that is already
on Redis is safe to send again.
"""

import logging

from remitx_api.config import Config
from remitx_api.models.orm.integration_message import STATUS_PENDING, IntegrationMessage
from sqlalchemy import select

from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope

PROCESS_INTEGRATION_MESSAGE = "remitx_worker.tasks.process_integration_message"

logger = logging.getLogger(__name__)


def reclaim_pending_messages() -> int:
    with session_scope() as session:
        ids = list(
            session.scalars(
                select(IntegrationMessage.id).where(
                    IntegrationMessage.status == STATUS_PENDING
                )
            )
        )
    for message_id in ids:
        celery.send_task(
            PROCESS_INTEGRATION_MESSAGE,
            args=[str(message_id)],
            queue=Config.CELERY_QUEUE,
        )
    if ids:
        logger.info("reclaimed %s pending integration message(s)", len(ids))
    return len(ids)
