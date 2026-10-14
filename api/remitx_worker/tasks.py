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

from remitx_worker import evm_service
from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope

logger = logging.getLogger(__name__)

# How long `burn_treasury_tokens` waits for a burn's receipt, and how often and
# how many times it retries the wait before leaving the group for a person.
BURN_RECEIPT_TIMEOUT_SECONDS = 120
BURN_RECEIPT_RETRY_SECONDS = 60
BURN_RECEIPT_MAX_RETRIES = 10

# The burn hash column readers use. The only other place a hash column is
# named is `_burn_hash_values`.
_BURN_HASH_COLUMN = Transaction.evm_tx_hash


def _burn_hash_values(tx_hash: str) -> dict[str, str]:
    """The column values that record `tx_hash` on a quote's `token_burn` leg.

    `evm_tx_hash` is the column readers use. `xrpl_tx_hash` is its
    deprecated name (#239), written too while the rename's expand phase
    lets a worker on the previous release keep working.
    """
    return {"evm_tx_hash": tx_hash, "xrpl_tx_hash": tx_hash}


class _BurnHashNotRecorded(Exception):
    """`burn_treasury_tokens` could not store a signed burn's hash, so it
    did not send it."""


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


@celery.task(
    bind=True,
    name="remitx_worker.tasks.burn_treasury_tokens",
    max_retries=BURN_RECEIPT_MAX_RETRIES,
)
def burn_treasury_tokens(self, quote_id: str) -> str:
    """Burn a quote's UCTUSD from the Treasury Wallet on the XRPL EVM chain.

    Claims every one of the quote's pending transactions with a guarded
    transition to `processing`, so every transaction's `processed_at`
    reflects the moment settlement actually started. Only the delivery that
    makes that claim can send a burn, and it burns exactly the `token_burn`
    leg's amount (never what the Treasury holds: it also holds float).

    The burn's hash is stored on the burn leg after signing and before the
    send (`evm_service.burn_tokens`'s `on_signed`). Then the task waits for
    the receipt, and only a confirmed burn is handed to
    `confirm_treasury_burn`, which confirms and credits the group. A
    remittance is therefore never final before its burn is.

    A retry never sends a second burn. A delivery that finds the group
    already claimed waits on the stored hash, or does nothing if no hash was
    stored. If the receipt does not come, the task retries the wait
    (`BURN_RECEIPT_MAX_RETRIES` times, `BURN_RECEIPT_RETRY_SECONDS` apart),
    then leaves the group `processing` for a person, logged as
    `event=settlement.burn_unconfirmed`.
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
        if claimed.rowcount == 0:
            # Not ours to send. A redelivery of a burn that was already
            # signed waits on the stored hash instead.
            burn_leg = session.execute(
                select(Transaction.status, _BURN_HASH_COLUMN).where(
                    Transaction.quote_id == target_id,
                    Transaction.type == TYPE_TOKEN_BURN,
                )
            ).first()
        else:
            amount = session.execute(
                select(Transaction.amount).where(
                    Transaction.quote_id == target_id,
                    Transaction.type == TYPE_TOKEN_BURN,
                    Transaction.status == TX_STATUS_PROCESSING,
                )
                # The amount of the token burn leg just claimed
            ).scalar_one()

    if claimed.rowcount == 0:
        return _resume_burn(self, quote_id, burn_leg)

    recorded: list[str] = []

    def record(tx_hash: str) -> None:
        # Its own commit, before the send: a crash after this point leaves
        # the hash for a retry to wait on.
        with session_scope() as session:
            stored = session.execute(
                update(Transaction)
                .where(
                    Transaction.quote_id == target_id,
                    Transaction.type == TYPE_TOKEN_BURN,
                    Transaction.status == TX_STATUS_PROCESSING,
                    _BURN_HASH_COLUMN.is_(None),
                )
                .values(**_burn_hash_values(tx_hash))
                .execution_options(synchronize_session=False)
            )
        if stored.rowcount != 1:
            raise _BurnHashNotRecorded(tx_hash)
        recorded.append(tx_hash)

    try:
        tx_hash = evm_service.burn_tokens(amount, on_signed=record)
    except _BurnHashNotRecorded as exc:
        # The leg left `processing` or gained a hash between the claim and
        # now. Nothing was sent, and the leg is not this delivery's to fail.
        logger.error(
            "event=settlement.burn_not_recorded quote_id=%s tx_hash=%s: the burn "
            "leg was no longer processing without a hash, so the signed burn "
            "was not sent",
            quote_id,
            exc,
        )
        return "skipped"
    except Exception as exc:
        if not recorded:
            # Failed before signing finished: nothing reached the chain.
            logger.exception(
                "burn failed for quote %s (amount=%s); nothing was sent",
                quote_id,
                amount,
            )
            queue_service.enqueue_confirm_treasury_burn(quote_id, None, str(exc))
            return "burn_failed"
        # The hash is stored, so the send may have reached the chain even
        # though it raised. Failing the group now could fail a burn that
        # lands; wait on the hash instead.
        (tx_hash,) = recorded
        logger.warning(
            "event=settlement.burn_send_uncertain quote_id=%s tx_hash=%s: the "
            "send raised after the hash was stored (%s); waiting on the hash",
            quote_id,
            tx_hash,
            type(exc).__name__,
        )

    return _await_burn(self, quote_id, tx_hash)


def _resume_burn(task, quote_id: str, burn_leg) -> str:
    """A delivery that found nothing pending to claim: never sends."""
    if burn_leg is None or burn_leg.status != TX_STATUS_PROCESSING:
        logger.info(
            "quote %s has no pending transactions; already burned or unknown",
            quote_id,
        )
        return "skipped"
    tx_hash = burn_leg[1]
    if tx_hash is None:
        # Either another delivery is signing right now, or a worker stopped
        # after the claim and before signing, in which case nothing was sent.
        # Telling those apart needs a person.
        logger.warning(
            "event=settlement.burn_unsigned quote_id=%s: the group is "
            "processing but no burn hash is stored; not sending a burn",
            quote_id,
        )
        return "skipped"
    logger.info(
        "event=settlement.burn_resumed quote_id=%s tx_hash=%s: waiting on the "
        "stored burn instead of sending another",
        quote_id,
        tx_hash,
    )
    return _await_burn(task, quote_id, tx_hash)


def _await_burn(task, quote_id: str, tx_hash: str) -> str:
    """Wait for the burn's receipt, then hand the outcome to the confirm task."""
    try:
        evm_service.wait_for_receipt(tx_hash, timeout=BURN_RECEIPT_TIMEOUT_SECONDS)
    except evm_service.TransactionReverted as exc:
        # Mined and failed: no tokens were burned, so the group can fail.
        logger.error(
            "event=settlement.burn_reverted quote_id=%s tx_hash=%s",
            quote_id,
            tx_hash,
        )
        queue_service.enqueue_confirm_treasury_burn(quote_id, None, str(exc))
        return "burn_failed"
    except Exception as exc:
        # No answer (a timeout, or the RPC unreachable): the burn may still
        # be mined. Never fail it from here; wait on the same hash again.
        if task.request.retries >= task.max_retries:
            logger.error(
                "event=settlement.burn_unconfirmed quote_id=%s tx_hash=%s "
                "retries=%s: no receipt, so the group is left processing for "
                "a person. Look the hash up on the explorer: if no such "
                "transaction exists it was never broadcast and nothing was "
                "burned",
                quote_id,
                tx_hash,
                task.request.retries,
            )
            return "awaiting_receipt"
        logger.warning(
            "event=settlement.burn_receipt_retry quote_id=%s tx_hash=%s retry=%s (%s)",
            quote_id,
            tx_hash,
            task.request.retries + 1,
            type(exc).__name__,
        )
        raise task.retry(countdown=BURN_RECEIPT_RETRY_SECONDS, exc=exc) from None

    queue_service.enqueue_confirm_treasury_burn(quote_id, tx_hash)
    return "burned"


@celery.task(name="remitx_worker.tasks.confirm_treasury_burn")
def confirm_treasury_burn(
    quote_id: str, tx_hash: str | None, error: str | None = None
) -> str:
    """Record the outcome of `burn_treasury_tokens`'s EVM burn.

    On success, confirm and credit *every* remittance transactions in one commit.

    Guarded on `status IN ('pending', 'processing')`, which catches every
    transaction that's still waiting that was claimed together by
    `burn_treasury_tokens`.

    `tx_hash` is given only once the burn's receipt has confirmed it.
    `tx_hash is None` indicated a token burn failure (nothing sent, or the
    burn reverted). Therefore, every transaction the `quote_id` is set to
    `failed`. Only transaction status changes as no account balances were
    changed.

    A failed group sits and needs manual investigation. Groups stuck in
    ``processing`` are only logged by ``reclaim_stuck_settlements``; fully
    ``pending`` groups are re-enqueued by ``reclaim_pending_settlements``.

    `error` (the original exception's message, from `burn_treasury_tokens`)
    is logged alongside that failure so the worker's log stream shows the
    actual reason next to the group that got marked `failed`, not just the
    fact of it.
    """
    try:
        # get the quote_id as a UUID object
        target_id = uuid.UUID(quote_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("quote id %r is not a valid id; skipping", quote_id)
        return "skipped"

    in_flight = (TX_STATUS_PENDING, TX_STATUS_PROCESSING)

    # No hash means the burn failed, so mark all legs as failed
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
            .values(**_burn_hash_values(tx_hash))
            # Add the token burn success hash to the token burn
            # transaction row (already stored before the send; the same
            # value, written again)
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
