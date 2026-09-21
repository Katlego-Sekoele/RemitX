import logging
import uuid

from remitx_api.clock import utcnow
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.integration_message import (
    STATUS_PENDING,
    STATUS_PROCESSED,
    IntegrationMessage,
)
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    Transaction,
)
from remitx_api.models.orm.transaction import (
    STATUS_PENDING as TX_STATUS_PENDING,
)
from sqlalchemy import select, update

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

    This relies on READ COMMITTED, Postgres's default: a concurrent duplicate
    blocks on the row lock, then re-evaluates its WHERE against the committed
    row and matches nothing. Under REPEATABLE READ or SERIALIZABLE the second
    transaction would instead raise a serialization error, redeliver, and skip
    on the retry — still correct, just noisier.
    """
    try:
        target_id = uuid.UUID(message_id)
    except (AttributeError, TypeError, ValueError):
        # Same contract as an unknown id: nothing to do, and raising would only
        # turn a bad message into a task failure.
        logger.warning("integration message %r is not a valid id; skipping", message_id)
        return "skipped"

    with session_scope() as session:
        result = session.execute(
            update(IntegrationMessage)
            .where(
                IntegrationMessage.id == target_id,
                IntegrationMessage.status == STATUS_PENDING,
            )
            .values(status=STATUS_PROCESSED, processed_at=utcnow())
            .execution_options(synchronize_session=False)
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


@celery.task(name="remitx_worker.tasks.settle_remittance")
def settle_remittance(quote_id: str) -> str:
    """Confirm every pending ledger leg sharing `quote_id` and credit each
    leg's destination account, in one commit (Transaction_Flow_Context.md
    §2 Phase C).

    Same guarded-update idempotency as `process_integration_message`,
    widened from one `tx_id` to a whole `quote_id` group: a redelivered
    message's guarded UPDATE matches nothing once the first delivery
    committed, so this is safe to run more than once. Because the group
    UPDATE is one atomic, guarded statement, a nonzero rowcount means every
    leg in the group just confirmed together in *this* call — the follow-up
    SELECT can never observe a group partially confirmed by another call.
    """
    try:
        target_id = uuid.UUID(quote_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("quote id %r is not a valid id; skipping", quote_id)
        return "skipped"

    with session_scope() as session:
        result = session.execute(
            update(Transaction)
            .where(
                Transaction.quote_id == target_id,
                Transaction.status == TX_STATUS_PENDING,
            )
            .values(status=STATUS_CONFIRMED, confirmed_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 0:
            logger.info(
                "quote %s has no pending legs; already settled or unknown",
                quote_id,
            )
            return "skipped"

        legs = session.execute(
            select(Transaction.debit_account_id, Transaction.amount).where(
                Transaction.quote_id == target_id,
                Transaction.status == STATUS_CONFIRMED,
            )
        ).all()
        for debit_account_id, amount in legs:
            session.execute(
                update(Account)
                .where(Account.account_id == debit_account_id)
                .values(account_balance=Account.account_balance + amount)
            )

    logger.info("quote %s settled: %d legs confirmed", quote_id, len(legs))
    return "settled"
