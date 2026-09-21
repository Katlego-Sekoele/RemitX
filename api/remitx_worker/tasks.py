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
    STATUS_FAILED,
    STATUS_PROCESSING,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.models.orm.transaction import (
    STATUS_PENDING as TX_STATUS_PENDING,
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
    """Kick off a remittance's settlement (Transaction_Flow_Context.md §2
    Phase C).

    None of a remittance's seven legs confirm here, or anywhere, until the
    treasury's on-chain burn resolves — this task's only job is handing off
    to `burn_treasury_tokens`, which does the one guard the whole pipeline
    needs (claiming the `burn` leg before submitting it to the XRPL
    testnet). Gating every leg on the burn, not just the beneficiary payout,
    means a failed burn needs no reversal: nothing was ever credited, so
    `confirm_treasury_burn` marking the whole group `failed` is a pure
    status flip, not an undo.

    Read-only check, not a guarded UPDATE — this task doesn't itself
    transition anything, so there's no race to guard against here; the
    burn leg's own claim is what makes redelivery safe.
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
        ).first()

    if pending_burn_leg is None:
        logger.info(
            "quote %s has no pending burn leg; already settling or unknown",
            quote_id,
        )
        return "skipped"

    queue_service.enqueue_burn_treasury_tokens(quote_id)
    return "queued"


@celery.task(name="remitx_worker.tasks.burn_treasury_tokens")
def burn_treasury_tokens(quote_id: str) -> str:
    """Submit a quote's treasury `burn` leg as a real XRPL `Payment`
    (Transaction_Flow_Context.md §2 Phase C).

    Claims the pending `burn` leg with a guarded transition to a new
    `processing` status rather than the usual pending->confirmed guard,
    because unlike every other leg here there's a real network call sitting
    between "claimed" and "done" — a redelivered task must not submit the
    same burn twice while the first is still in flight.

    Deliberately does nothing else once the XRPL call resolves: recording
    the result — confirming the leg, storing its hash, crediting balances,
    releasing the beneficiary payout — is handed to a *sequential* follow-up
    task, `confirm_treasury_burn`, so that DB-only step never has to share a
    task invocation with a slow external call, and can be safely retried
    entirely on its own if it fails partway.
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
                Transaction.type == TYPE_TOKEN_BURN,
                Transaction.status == TX_STATUS_PENDING,
            )
            .values(status=STATUS_PROCESSING)
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount == 0:
            logger.info(
                "quote %s has no pending burn leg; already burned or unknown",
                quote_id,
            )
            return "skipped"

        amount = session.execute(
            select(Transaction.amount).where(
                Transaction.quote_id == target_id,
                Transaction.type == TYPE_TOKEN_BURN,
                Transaction.status == STATUS_PROCESSING,
            )
        ).scalar_one()

    try:
        tx_hash = xrpl_service.burn_tokens(amount)
    except Exception:
        logger.exception("burn failed for quote %s", quote_id)
        queue_service.enqueue_confirm_treasury_burn(quote_id, None)
        return "burn_failed"

    queue_service.enqueue_confirm_treasury_burn(quote_id, tx_hash)
    return "burned"


@celery.task(name="remitx_worker.tasks.confirm_treasury_burn")
def confirm_treasury_burn(quote_id: str, tx_hash: str | None) -> str:
    """Record the outcome of `burn_treasury_tokens`'s XRPL call — and only
    on success, confirm and credit *every* leg of the remittance together,
    in one commit (Transaction_Flow_Context.md §2 Phase C).

    Pure DB work, no network call — so unlike `burn_treasury_tokens` this is
    trivially safe to retry on its own. Guarded on `status IN ('pending',
    'processing')`, which catches every leg that's still waiting: the burn
    leg itself sits in `processing` (claimed by `burn_treasury_tokens`),
    the other six are still `pending` (nothing else in this pipeline
    confirms anything before this task runs). Same idempotency shape as
    every other guarded transition in this module: a redelivered message
    matches nothing once the first delivery committed.

    `tx_hash is None` means the burn itself failed — every leg sharing this
    `quote_id` flips straight to `failed`. That's a pure status change, not
    a reversal: nothing was ever credited, since confirmation for the whole
    remittance was always gated on this one call resolving. A failed group
    just sits there for manual investigation — there's no automatic
    retry/reclaim for a stuck `transactions` row yet (only
    `IntegrationMessage` has one, via `remitx_worker/reclaim.py`).
    """
    try:
        target_id = uuid.UUID(quote_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("quote id %r is not a valid id; skipping", quote_id)
        return "skipped"

    in_flight = (TX_STATUS_PENDING, STATUS_PROCESSING)

    if tx_hash is None:
        with session_scope() as session:
            result = session.execute(
                update(Transaction)
                .where(
                    Transaction.quote_id == target_id,
                    Transaction.status.in_(in_flight),
                )
                .values(status=STATUS_FAILED)
                .execution_options(synchronize_session=False)
            )
        if result.rowcount == 0:
            return "skipped"
        logger.info(
            "quote %s burn failed: %d legs marked failed, nothing was credited",
            quote_id,
            result.rowcount,
        )
        return "failed"

    with session_scope() as session:
        confirmed = session.execute(
            update(Transaction)
            .where(
                Transaction.quote_id == target_id,
                Transaction.status.in_(in_flight),
            )
            .values(status=STATUS_CONFIRMED, confirmed_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if confirmed.rowcount == 0:
            logger.info(
                "quote %s has no in-flight legs; already settled or unknown",
                quote_id,
            )
            return "skipped"

        # Only the burn leg carries the XRPL hash.
        session.execute(
            update(Transaction)
            .where(
                Transaction.quote_id == target_id,
                Transaction.type == TYPE_TOKEN_BURN,
            )
            .values(xrpl_tx_hash=tx_hash)
        )

        legs = session.execute(
            select(
                Transaction.credit_account_id,
                Transaction.debit_account_id,
                Transaction.amount,
            ).where(
                Transaction.quote_id == target_id,
                Transaction.status == STATUS_CONFIRMED,
            )
        ).all()
        # Every destination credited before any source is debited: the
        # sender's and beneficiary's own token accounts are each a
        # destination in one leg and a source in another within this same
        # batch, and Account's CHECK(type <> 'USER' OR account_balance >= 0)
        # is checked per-statement, not deferred — debiting one of those
        # accounts before its matching credit lands would transiently dip it
        # negative and fail the constraint, even though the batch nets out.
        for _credit_account_id, debit_account_id, amount in legs:
            session.execute(
                update(Account)
                .where(Account.account_id == debit_account_id)
                .values(account_balance=Account.account_balance + amount)
            )
        for credit_account_id, _debit_account_id, amount in legs:
            # credit_account_id is the source (models/orm/transaction.py) —
            # debited here so a settled leg actually leaves the paying
            # account's balance, not just credits the receiving one.
            session.execute(
                update(Account)
                .where(Account.account_id == credit_account_id)
                .values(account_balance=Account.account_balance - amount)
            )

    logger.info(
        "quote %s burned (%s): %d legs confirmed and settled",
        quote_id,
        tx_hash,
        len(legs),
    )
    return "settled"
