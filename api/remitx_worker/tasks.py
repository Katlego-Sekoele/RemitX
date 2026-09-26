import logging
import uuid

from remitx_api.clock import utcnow
from remitx_api.models.orm.account import Account

# Both models name their status constants identically (STATUS_PENDING,
# etc.), with different values (IntegrationMessage's are uppercase,
# Transaction's lowercase) — IM_/TX_ prefixed on import so both sets can
# coexist in this one file without one silently shadowing the other.
from remitx_api.models.orm.integration_message import (
    STATUS_PENDING as IM_STATUS_PENDING,
    STATUS_PROCESSED as IM_STATUS_PROCESSED,
    IntegrationMessage,
)
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED as TX_STATUS_CONFIRMED,
    STATUS_FAILED as TX_STATUS_FAILED,
    STATUS_PENDING as TX_STATUS_PENDING,
    STATUS_PROCESSING as TX_STATUS_PROCESSING,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.services import queue_service
from sqlalchemy import select, update

from remitx_worker import xrpl_service
from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope

logger = logging.getLogger(__name__)


@celery.task(name="remitx_worker.tasks.ping")
def ping():
    return "pong"


@celery.task(name="remitx_worker.tasks.reclaim_stuck_settlements")
def reclaim_stuck_settlements() -> str:
    """Periodic reclaim for settlement groups lost off the broker."""
    from remitx_api.config import Config
    from remitx_worker.reclaim import (
        log_stale_processing_settlements,
        reclaim_pending_settlements,
    )

    pending = reclaim_pending_settlements(
        min_age_seconds=Config.SETTLEMENT_RECLAIM_MIN_AGE_SECONDS
    )
    stale = log_stale_processing_settlements(
        min_age_seconds=Config.SETTLEMENT_PROCESSING_STALE_LOG_SECONDS
    )
    return f"pending={pending} stale_logged={stale}"


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
                IntegrationMessage.status == IM_STATUS_PENDING,
            )
            .values(status=IM_STATUS_PROCESSED, processed_at=utcnow())
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
    """Kick off a remittance's settlement

    Task's only job is handing off to `burn_treasury_tokens`.
    """
    try:
        target_id = uuid.UUID(quote_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("quote id %r is not a valid id; skipping", quote_id)
        return "skipped"

    with session_scope() as session:
        pending_burn_leg = session.execute(
            select(Transaction.tx_id).where(
                Transaction.quote_id == target_id,
                Transaction.type == TYPE_TOKEN_BURN,
                Transaction.status == TX_STATUS_PENDING,
            )
            # Get the first pending token burn transaction for the given quote_id
        ).first()

    if pending_burn_leg is None:
        logger.info(
            "quote %s has no pending token burn transaction; already "
            "settling or unknown",
            quote_id,
        )
        return "skipped"

    # Enqueue the burn treasury tokens task for the given quote_id
    queue_service.enqueue_burn_treasury_tokens(quote_id)
    return "queued"


@celery.task(name="remitx_worker.tasks.burn_treasury_tokens")
def burn_treasury_tokens(quote_id: str) -> str:
    """Submit a quote's treasury `burn` token transaction as a real XRPL `Payment`

    Claim every one of the quote's pending transactions with a guarded transition
    to a new `processing` status so every transaction's `processed_at` reflects the
    moment settlement actually started.

    Does nothing else once the XRPL call resolves: recording
    the result is handed to `confirm_treasury_burn`, so that
    the DB changes can be made in a separate, isolated task.
    """
    try:
        target_id = uuid.UUID(quote_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("quote id %r is not a valid id; skipping", quote_id)
        return "skipped"

    with session_scope() as session:
        claimed = session.execute(
            update(Transaction)
            .where(
                Transaction.quote_id == target_id,
                Transaction.status == TX_STATUS_PENDING,
            )
            .values(status=TX_STATUS_PROCESSING, processed_at=utcnow())
            .execution_options(synchronize_session=False)
            # Get all transactions with the given quote_id and pending
            # status, and update their status to processing
        )
        # if no rows were updated, log that the quote has no pending
        # transactions and return "skipped"
        if claimed.rowcount == 0:
            logger.info(
                "quote %s has no pending transactions; already burned or unknown",
                quote_id,
            )
            return "skipped"

        amount = session.execute(
            select(Transaction.amount).where(
                Transaction.quote_id == target_id,
                Transaction.type == TYPE_TOKEN_BURN,
                Transaction.status == TX_STATUS_PROCESSING,
            )
            # Get the amount of the pending token burn transaction for the
            # given quote_id
        ).scalar_one()

    # Try to burn the tokens by calling the xrpl_service.burn_tokens
    # function with the amount.
    try:
        tx_hash = xrpl_service.burn_tokens(amount)
    except Exception as exc:
        logger.exception("burn failed for quote %s (amount=%s)", quote_id, amount)
        # if the burn fails, enqueue the confirm_treasury_burn task with
        # None as the tx_hash and the exception message as the error
        queue_service.enqueue_confirm_treasury_burn(quote_id, None, str(exc))
        return "burn_failed"

    queue_service.enqueue_confirm_treasury_burn(quote_id, tx_hash)
    return "burned"


@celery.task(name="remitx_worker.tasks.confirm_treasury_burn")
def confirm_treasury_burn(
    quote_id: str, tx_hash: str | None, error: str | None = None
) -> str:
    """Record the outcome of `burn_treasury_tokens`'s XRPL call.

    On success, confirm and credit *every* remittance transactions in one commit.

    Guarded on `status IN ('pending', 'processing')`, which catches every
    transaction that's still waiting that was claimed together by
    `burn_treasury_tokens`.

    `tx_hash is None` indicated a token burn failure. Therefore, every
    transaction the `quote_id` is set to `failed`. Only transaction status
    changes as no account balances were changed.

    A failed group sits and needs manual investigation. Groups stuck in
    ``processing`` are only logged by ``reclaim_stuck_settlements``; fully
    ``pending`` groups are re-enqueued by ``reclaim_pending_settlements``.

    `error`(the original XRPL exception's message, from `burn_treasury_tokens`) is
    logged alongside that failure so Render's log stream shows the actual
    reason next to the group that got marked `failed`, not just the fact of
    it.
    """
    try:
        # get the quote_id as a UUID object
        target_id = uuid.UUID(quote_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("quote id %r is not a valid id; skipping", quote_id)
        return "skipped"

    in_flight = (TX_STATUS_PENDING, TX_STATUS_PROCESSING)

    # No XRPL hash means the burn failed, so mark all legs as failed
    if tx_hash is None:
        with session_scope() as session:
            result = session.execute(
                update(Transaction)
                .where(
                    Transaction.quote_id == target_id,
                    Transaction.status.in_(in_flight),
                )
                .values(status=TX_STATUS_FAILED)
                .execution_options(synchronize_session=False)
                # Get transactions with the given quote_id and in-flight
                # status, and update their status to failed
            )
        # if no rows were updated, log that the quote has no pending or
        # processing transactions and return "skipped"
        if result.rowcount == 0:
            logger.info(
                "quote %s has no pending or processing transactions; "
                "already settled or unknown",
                quote_id,
            )
            return "skipped"
        logger.error(
            "quote %s burn failed (%s): %d transactions marked failed, no "
            "account balances have been changed, no account balances have "
            "been updated",
            quote_id,
            error or "unknown error",
            result.rowcount,
        )
        return "failed"

    # Else if the burn succeeded, confirm and settle all legs in one
    # commit, updating account balances accordingly.
    with session_scope() as session:
        confirmed = session.execute(
            update(Transaction)
            .where(
                Transaction.quote_id == target_id,
                Transaction.status.in_(in_flight),
            )
            .values(status=TX_STATUS_CONFIRMED, confirmed_at=utcnow())
            .execution_options(synchronize_session=False)
            # Update all transactions with the given quote_id and
            # in-flight status to confirmed, and set their confirmed_at
            # timestamp to now
        )
        if confirmed.rowcount == 0:
            logger.info(
                "quote %s has no processing or pending transactions; "
                "already settled or unknown",
                quote_id,
            )
            return "skipped"

        session.execute(
            update(Transaction)
            .where(
                Transaction.quote_id == target_id,
                Transaction.type == TYPE_TOKEN_BURN,
            )
            .values(xrpl_tx_hash=tx_hash)
            # Add the token burn success hash to the token burn
            # transaction row
        )

        remittance_transactions = session.execute(
            select(
                Transaction.credit_account_id,
                Transaction.debit_account_id,
                Transaction.amount,
            ).where(
                Transaction.quote_id == target_id,
                Transaction.status == TX_STATUS_CONFIRMED,
            )
            # Get all confirmed transactions for the given remittance
            # quote_id, and select their credit_account_id,
            # debit_account_id, and amount
        ).all()

        # Update the debited account balances first, then the credited
        # account balances, to avoid any potential issues with negative
        # balances or overdrafts.
        for _credit_account_id, debit_account_id, amount in remittance_transactions:
            session.execute(
                update(Account)
                .where(Account.account_id == debit_account_id)
                .values(account_balance=Account.account_balance + amount)
                # Update the account balance of the debit_account_id by
                # adding the amount to it, for each remittance transaction
                # in the list of confirmed transactions
            )
        for credit_account_id, _debit_account_id, amount in remittance_transactions:
            session.execute(
                update(Account)
                .where(Account.account_id == credit_account_id)
                .values(account_balance=Account.account_balance - amount)
            )
            # Update the account balance of the credit_account_id by
            # subtracting the amount from it, for each remittance
            # transaction in the list of confirmed transactions
    logger.info(
        "quote %s burned (%s): %d transactions confirmed and settled",
        quote_id,
        tx_hash,
        len(remittance_transactions),
    )
    return "settled"
