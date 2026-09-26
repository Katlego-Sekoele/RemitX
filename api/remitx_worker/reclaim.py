"""Re-enqueue work after a broker wipe or a lost publish.

Free Render Key Value is in-memory and may restart empty. Postgres is the
source of truth; this walks leftover PENDING integration messages and
remittance settlement groups back onto the queue.

``process_integration_message`` and ``settle_remittance`` are idempotent at
their entry guards, so a message that is already on Redis is safe to send
again. Only remittance groups whose seven legs are still fully ``pending``
are re-enqueued — groups in ``processing`` may have an XRPL burn in flight
and are never blindly retried here.
"""

import logging
from datetime import timedelta

from remitx_api.clock import utcnow
from remitx_api.config import Config
from remitx_api.models.orm.integration_message import STATUS_PENDING, IntegrationMessage
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_PENDING as TX_STATUS_PENDING,
    STATUS_PROCESSING as TX_STATUS_PROCESSING,
    TYPE_TOKEN_BURN,
    Transaction,
)
from sqlalchemy import exists, not_, select

from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope

PROCESS_INTEGRATION_MESSAGE = "remitx_worker.tasks.process_integration_message"
SETTLE_REMITTANCE = "remitx_worker.tasks.settle_remittance"

logger = logging.getLogger(__name__)


def reclaim_on_worker_boot() -> None:
    """Broker-empty startup: re-enqueue every safe pending row immediately."""
    reclaim_pending_messages()
    reclaim_pending_settlements(min_age_seconds=0)


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


def _pending_settlement_quote_ids(
    session, *, min_age_seconds: int
) -> list:
    pending_burn = (
        select(Transaction.tx_id)
        .where(
            Transaction.quote_id == Remittance.quote_id,
            Transaction.type == TYPE_TOKEN_BURN,
            Transaction.status == TX_STATUS_PENDING,
        )
        .correlate(Remittance)
    )
    non_pending_leg = (
        select(Transaction.tx_id)
        .where(
            Transaction.quote_id == Remittance.quote_id,
            Transaction.status != TX_STATUS_PENDING,
        )
        .correlate(Remittance)
    )
    stmt = select(Remittance.quote_id).where(
        exists(pending_burn),
        not_(exists(non_pending_leg)),
    )
    if min_age_seconds > 0:
        cutoff = utcnow() - timedelta(seconds=min_age_seconds)
        stmt = stmt.where(Remittance.created_at <= cutoff)
    return list(session.scalars(stmt))


def reclaim_pending_settlements(min_age_seconds: int) -> int:
    """Re-enqueue ``settle_remittance`` for groups still fully ``pending``.

    ``min_age_seconds`` is ignored when zero (worker boot). When positive,
    only remittances at least that old are reclaimed so a confirm that
    enqueued milliseconds ago is not duplicated on every beat tick.
    """
    with session_scope() as session:
        quote_ids = _pending_settlement_quote_ids(
            session, min_age_seconds=min_age_seconds
        )
    for quote_id in quote_ids:
        celery.send_task(
            SETTLE_REMITTANCE,
            args=[str(quote_id)],
            queue=Config.CELERY_QUEUE,
        )
    if quote_ids:
        logger.info(
            "reclaimed %s pending settlement group(s) (min_age=%ss)",
            len(quote_ids),
            min_age_seconds,
        )
    return len(quote_ids)


def log_stale_processing_settlements(min_age_seconds: int) -> int:
    """Log settlement groups stuck in ``processing``; never re-enqueue them."""
    cutoff = utcnow() - timedelta(seconds=min_age_seconds)
    with session_scope() as session:
        quote_ids = list(
            session.scalars(
                select(Transaction.quote_id)
                .where(
                    Transaction.quote_id.isnot(None),
                    Transaction.status == TX_STATUS_PROCESSING,
                    Transaction.processed_at.isnot(None),
                    Transaction.processed_at <= cutoff,
                )
                .distinct()
            )
        )
    for quote_id in quote_ids:
        logger.warning(
            "settlement quote %s still processing (processed_at <= %s); "
            "manual investigation required — not auto-reclaiming",
            quote_id,
            cutoff.isoformat(),
        )
    return len(quote_ids)
