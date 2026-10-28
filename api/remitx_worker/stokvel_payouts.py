"""Paying a released stokvel pool out to the beneficiary.

Once a round's release is recorded (`stokvel_ledger.record_pool_release`),
the pool is in the Treasury Wallet. `stokvel.settle_payout(payout_id)` turns
it into a normal remittance, with the stokvel as the quote's sender and
the scheduled member's chosen Payout beneficiary as the recipient:

- one quote, priced by `quote_service.price_stokvel_payout`, containing the
  full amount released from the pool, no fee or margin (the members paid the
  fee on top of their contributions), and no sending limits. It is accepted
  at once (`USED`) as there is no customer to accept it
- its pending legs, sharing the quote's `quote_id` as settlement expects. The
  pool is paid from the Treasury Wallet, where the release put it, not back
  through `STOKVEL`:

      Treasury -> beneficiary token         remittance (the remittance's leg)
      beneficiary token -> Treasury         remittance
      Treasury -> token issuer              token_burn
      RemitX bank -> beneficiary fiat       beneficiary_payout

  No fiat comes in and no fee is taken, so a user remittance's first three
  legs have no counterpart here
- one remittance, and the payout's `remittance_status` `pending ->
  processing` with its `quote_id` and `remittance_id`, in the same commit

It hands the remittance to the existing settlement chain:

    `settle_remittance` -> `burn_treasury_tokens` -> `confirm_treasury_burn`

the chain a user's remittance takes, with its guards against a second burn or
credit. A lost hand-off leaves the legs fully pending, which the reclaim sweep
queues again. `confirm_treasury_burn` finishes the payout through
`record_settlement`, in the commit that settles or fails its legs, so the
payout can never disagree with them.

Queued by `queue_released_payouts`, which the event sync runs at the end of
every run, for every released payout not yet started. Repeating it is
harmless: only the delivery whose guarded update succeeds creates anything.
A payout whose beneficiary no longer fits (deleted, another payout currency,
no account to credit) is marked `failed` for a person, rather than guessed at.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from remitx_api.config import Config
from remitx_api.db.request_db_session import (
    reset_request_db_session,
    set_request_db_session,
)
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    TYPE_PLATFORM_FIAT,
    Account,
)
from remitx_api.models.orm.beneficiary import Beneficiary
from remitx_api.models.orm.quote import STATUS_USED, Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_REMITTANCE,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.services import exchange_rate_service, queue_service, quote_service
from sqlalchemy import func, or_, select, update

from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope
from remitx_worker.stokvel_ledger import RELEASED, treasury_account_id

logger = logging.getLogger(__name__)

# Released payouts queued per sync run, the longest waiting first.
_QUEUE_LIMIT = 50
# How long the sync leaves a payout it queued before queuing it again: long
# enough for a busy or cold worker to take the first message, short enough
# that a lost message or a rate that could not be fetched is retried soon.
REQUEUE_AFTER = timedelta(minutes=5)


class _AlreadyStarted(Exception):
    """Another delivery created this payout's quote first."""


class _DeploymentFault(Exception):
    """A platform account the payout's legs need is missing (seeded by
    migration, so a deployment fault, not something a retry fixes)."""


def queue_released_payouts() -> int:
    """Queue `stokvel.settle_payout` for each released payout whose remittance
    has not started, and return how many were queued.

    The event sync calls this after every run, so a payout is picked up
    within one sync interval and a lost message is sent again.

    A payout is due once released, then again only `REQUEUE_AFTER` after it was last
    queued (`settle_queued_at`), so a busy worker is not sent a pile of
    copies. That column is separate from `updated_at` so that other writes to
    the row do not delay it.

    The longest-waiting payouts go first, so a few
    that keep failing cannot block the rest.
    """
    now = datetime.now(UTC)
    # The conditions for a payout to be due: released, its remittance not
    # started, and not queued recently.
    due = (
        StokvelPayout.release_status == RELEASED,
        StokvelPayout.remittance_status == STATUS_PENDING,
        StokvelPayout.quote_id.is_(None),
        or_(
            StokvelPayout.settle_queued_at.is_(None),
            StokvelPayout.settle_queued_at < now - REQUEUE_AFTER,
        ),
    )
    with session_scope() as session:
        # Get the ids of the due payouts, longest-waiting first, up to the limit.
        payout_ids = session.scalars(
            select(StokvelPayout.id)
            .where(*due)
            .order_by(
                func.coalesce(StokvelPayout.settle_queued_at, StokvelPayout.released_at)
            )
            .limit(_QUEUE_LIMIT)
        ).all()
        # If any payouts are due, update their `settle_queued_at` to now so they are not
        # queued again until `REQUEUE_AFTER`.
        if payout_ids:
            session.execute(
                update(StokvelPayout)
                .where(StokvelPayout.id.in_(payout_ids), *due)
                .values(settle_queued_at=now)
                .execution_options(synchronize_session=False)
            )
    # Loop through the payout ids and enqueue a task to settle each payout.
    for payout_id in payout_ids:
        queue_service.enqueue_settle_payout(str(payout_id))
    return len(payout_ids)


@celery.task(name="stokvel.settle_payout")
def settle_payout(payout_id: str) -> str:
    """Turn a released payout into a quote, its legs and a remittance, then
    hand it to settlement.

    Returns what happened, for the log and the tests: `created`, `skipped`,
    `not_released`, `already_started`, `rate_unavailable` or `failed`."""
    try:
        # Get the payout id as a UUID object
        target_id = uuid.UUID(payout_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("payout id %r is not a valid id; skipping", payout_id)
        return "skipped"

    with session_scope() as session:
        # Get payout row, or None if it does not exist
        payout = session.get(StokvelPayout, target_id)
        if payout is None:
            logger.info("payout %s does not exist; skipping", payout_id)
            return "skipped"
        if payout.release_status != RELEASED:
            logger.info("payout %s is not released; not paying out", payout_id)
            return "not_released"
        if payout.remittance_status != STATUS_PENDING or payout.quote_id is not None:
            logger.info("payout %s has already started; skipping", payout_id)
            return "already_started"
        # Get the member object, stokvel object, pool amount, and beneficiary object for
        # the payout
        member = session.get(StokvelCycleMember, (payout.cycle_id, payout.member_id))
        stokvel = session.scalar(
            select(Stokvel)
            .join(StokvelCycle, StokvelCycle.stokvel_id == Stokvel.id)
            .where(StokvelCycle.id == payout.cycle_id)
        )
        pool = session.get(Transaction, payout.release_tx_id).amount
        beneficiary = (
            None
            if member.payout_beneficiary_id is None
            else session.get(Beneficiary, member.payout_beneficiary_id)
        )
        problem = _beneficiary_problem(session, member, beneficiary)
        stokvel_id, stokvel_currency = stokvel.id, stokvel.currency
        payout_currency = member.payout_currency
        recipient_id = None if beneficiary is None else beneficiary.linked_user_id
    # If the beneficiary has a problem, mark the payout as failed and return the reason
    # code.
    if problem is not None:
        return _fail(target_id, problem)

    try:
        # Get the pricing and sender amount for the payout using the pool amount,
        # stokvel currency, and payout currency.
        # _price runs `quote_service.price_stokvel_payout` in its own session and
        # commits.
        pricing, sender_amount = _price(pool, stokvel_currency, payout_currency)
    except (
        exchange_rate_service.RateUnavailableError,
        exchange_rate_service.UnsupportedCurrencyError,
    ) as exc:
        # Left pending: the next sync run queues it again.
        logger.warning(
            "event=stokvel.payout_rate_unavailable payout_id=%s (%s): left "
            "pending; queued again on the next sync run",
            payout_id,
            exc,
        )
        return "rate_unavailable"

    try:
        # Try to create the remittance, quote, and legs for the payout in a new session.
        with session_scope() as session:
            remittance = _create_remittance(
                session,
                target_id,
                stokvel_id=stokvel_id,
                recipient_id=recipient_id,
                pricing=pricing,
                sender_amount=sender_amount,
            )
            remittance_id, quote_id = remittance.remittance_id, remittance.quote_id
    except _AlreadyStarted:
        logger.info("payout %s was started by another delivery", payout_id)
        return "already_started"
    except _DeploymentFault as exc:
        # Nothing a retry fixes: a person must seed the account. Marked failed
        # so it is not queued again every few minutes.
        logger.error(
            "event=stokvel.payout_platform_account_missing payout_id=%s (%s)",
            payout_id,
            exc,
        )
        return _fail(target_id, "platform_account_missing")

    logger.info(
        "event=stokvel.payout_remittance_created payout_id=%s quote_id=%s "
        "remittance_id=%s token_amount=%s receiver_amount=%s %s",
        payout_id,
        quote_id,
        remittance_id,
        pricing.token_amount,
        pricing.receiver_amount,
        pricing.receiver_payout_currency,
    )
    try:
        # Try to enqueue a task to settle the remittance, which will handle the payout's
        # legs and final settlement.
        queue_service.enqueue_settle_remittance(str(quote_id))
    except Exception as exc:
        # The remittance is committed and its legs are all pending, which is
        # what the reclaim sweep queues again, so the payout is only late.
        # The error's type only: a broker error may carry its URL.
        logger.error(
            "event=stokvel.payout_hand_off_failed payout_id=%s quote_id=%s (%s): "
            "settle_remittance was not queued; the reclaim sweep queues it",
            payout_id,
            quote_id,
            type(exc).__name__,
        )
    return "created"


def record_settlement(session, quote_id: uuid.UUID, burn_tx_hash: str | None):
    """Mark the payout for remittance `quote_id` as confirmed or failed.

    Called by `confirm_treasury_burn`. With a `burn_tx_hash` the payout
    becomes `confirmed` and stores the hash; with None it becomes `failed`.

    Only a `processing` payout changes, so a replay does nothing. Returns the
    payout's id, or None if nothing changed (including any remittance that
    is not a stokvel payout). The caller commits.
    """
    # Get stokvel payout id based on the quote_id.
    payout_id = session.scalar(
        select(StokvelPayout.id).where(StokvelPayout.quote_id == quote_id)
    )
    if payout_id is None:
        return None
    # Payout is failed or confirmed based on the presence of burn_tx_hash.
    values = (
        {"remittance_status": STATUS_FAILED}
        if burn_tx_hash is None
        else {"remittance_status": STATUS_CONFIRMED, "burn_tx_hash": burn_tx_hash}
    )
    # Update the payout's remittance_status and burn_tx_hash in the database.
    finished = session.execute(
        update(StokvelPayout)
        .where(
            StokvelPayout.id == payout_id,
            StokvelPayout.remittance_status == STATUS_PROCESSING,
        )
        .values(**values, updated_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    return payout_id if finished.rowcount == 1 else None


def _beneficiary_problem(session, member, beneficiary) -> str | None:
    """Return a reason code if the member's chosen beneficiary cannot be paid
    now, or None if it can."""
    if member.payout_beneficiary_id is None or member.payout_currency is None:
        return "no_payout_beneficiary"
    if beneficiary is None:
        return "beneficiary_deleted"
    if beneficiary.payout_currency != member.payout_currency:
        return "beneficiary_payout_currency_changed"
    if _user_account(session, beneficiary.linked_user_id, CURRENCY_TOKEN) is None:
        return "recipient_has_no_token_account"
    if (
        _user_account(session, beneficiary.linked_user_id, member.payout_currency)
        is None
    ):
        return "recipient_has_no_payout_currency_account"
    return None


def _price(pool, stokvel_currency: str, payout_currency: str):
    """Run `price_stokvel_payout` in its own session and commit."""
    with session_scope() as session:
        token = set_request_db_session(session)
        try:
            # Run and return the pricing and sender amount for the payout.
            return quote_service.price_stokvel_payout(
                pool, stokvel_currency, payout_currency
            )
        finally:
            reset_request_db_session(token)


def _create_remittance(
    session, payout_id, *, stokvel_id, recipient_id, pricing, sender_amount
) -> Remittance:
    """Create the payout's quote, its four pending remittance transaction legs and
    its remittance record. Move the payout record from `pending` to `processing`, all in
    one `session`.

    Raises `_AlreadyStarted` if another delivery got there first (the
    caller's rollback discards what was made here), or `_DeploymentFault` if
    the Treasury, bank or token issuer account is missing."""
    now = datetime.now(UTC)
    # Create the quote for the payout, accepted at once as there is no customer to
    # accept it.
    quote = Quote(
        stokvel_id=stokvel_id,
        beneficiary_user_id=recipient_id,
        sender_amount=sender_amount,
        sender_currency=pricing.sender_currency,
        sender_amount_zar=pricing.sender_amount_zar,
        sender_transaction_fee=pricing.sender_transaction_fee,
        token_amount=pricing.token_amount,
        token_name=pricing.token_name,
        fiat_to_token_exchange_rate_id=pricing.fiat_to_token_exchange_rate_id,
        fiat_to_token_exchange_rate=pricing.fiat_to_token_exchange_rate,
        fiat_exchange_rate_id=pricing.fiat_exchange_rate_id,
        fiat_exchange_rate=pricing.fiat_exchange_rate,
        exchange_rate_margin=pricing.exchange_rate_margin,
        receiver_amount=pricing.receiver_amount,
        receiver_currency=pricing.receiver_payout_currency,
        receiver_payout_fee=pricing.receiver_payout_fee,
        receiver_payout_estimate=pricing.receiver_payout_estimate,
        created_at=now,
        expires_at=now + timedelta(minutes=Config.QUOTE_TTL_MINUTES),
        # Accepted at once: there is no customer to accept a stokvel's quote.
        status=STATUS_USED,
    )
    session.add(quote)
    session.flush()
    # Get the Treasury Wallet account, the beneficiary's token and fiat accounts,
    # the bank's fiat account, and the token issuer's account. Raise a deployment fault
    # if any of these are missing.
    try:
        treasury = treasury_account_id(session)
    except RuntimeError as exc:
        raise _DeploymentFault(str(exc)) from exc
    beneficiary_token = _user_account(session, recipient_id, CURRENCY_TOKEN)
    beneficiary_fiat = _user_account(
        session, recipient_id, pricing.receiver_payout_currency
    )
    bank = session.scalar(
        select(Account.account_id).where(
            Account.type == TYPE_PLATFORM_FIAT,
            Account.account_currency == pricing.receiver_payout_currency,
        )
    )
    issuer = session.scalar(
        select(Account.account_id).where(Account.label == Config().UCTUSD_ISSUER_LABEL)
    )
    if bank is None or issuer is None:
        # Seeded by migration: a missing one is a deployment fault.
        raise _DeploymentFault(
            f"no {TYPE_PLATFORM_FIAT} {pricing.receiver_payout_currency} account "
            "or token issuer account"
        )

    # Helper function to add a pending leg on this quote.
    # Nested in here so it can see the quote and session without passing them around.
    def leg(type_, source, destination, amount, currency) -> Transaction:
        """Create one pending transaction leg on this quote, and return it."""
        row = Transaction(
            type=type_,
            credit_account_id=source,
            debit_account_id=destination,
            amount=amount,
            currency=currency,
            status=STATUS_PENDING,
            quote_id=quote.quote_id,
        )
        session.add(row)
        return row

    tokens = pricing.token_amount
    # Transaction record for the Treasury Wallet sending tokens to the beneficiary's
    # token account.
    paid_out = leg(TYPE_REMITTANCE, treasury, beneficiary_token, tokens, CURRENCY_TOKEN)
    # Transaction record for the beneficiary's token account sending tokens back to the
    # Treasury Wallet.
    leg(TYPE_REMITTANCE, beneficiary_token, treasury, tokens, CURRENCY_TOKEN)
    # Transaction record for the Treasury Wallet sending tokens to the token issuer for
    # burning.
    leg(TYPE_TOKEN_BURN, treasury, issuer, tokens, CURRENCY_TOKEN)
    # Transaction record for the RemitX bank sending fiat to the beneficiary's fiat
    # account.
    leg(
        TYPE_BENEFICIARY_PAYOUT,
        bank,
        beneficiary_fiat,
        pricing.receiver_amount,
        pricing.receiver_payout_currency,
    )
    session.flush()
    # Create the remittance for the payout, linking it to the quote and the first
    # transaction leg.
    remittance = Remittance(quote_id=quote.quote_id, tx_id=paid_out.tx_id)
    session.add(remittance)
    session.flush()

    claimed = session.execute(
        update(StokvelPayout)
        .where(
            StokvelPayout.id == payout_id,
            StokvelPayout.release_status == RELEASED,
            StokvelPayout.remittance_status == STATUS_PENDING,
            StokvelPayout.quote_id.is_(None),
        )
        .values(
            remittance_status=STATUS_PROCESSING,
            quote_id=quote.quote_id,
            remittance_id=remittance.remittance_id,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        # Rolls back the quote, legs and remittance with the session.
        raise _AlreadyStarted()
    return remittance


def _user_account(session, user_id, currency: str):
    """The user's account id in `currency`, or None if they have none."""
    return session.scalar(
        select(Account.account_id).where(
            Account.user_id == user_id,
            Account.account_currency == currency,
        )
    )


def _fail(payout_id: uuid.UUID, reason: str) -> str:
    """Mark the payout record `pending -> failed` without creating anything, and log
    it for a person to resolve. `reason` is a fixed code, never free text."""
    with session_scope() as session:
        session.execute(
            update(StokvelPayout)
            .where(
                StokvelPayout.id == payout_id,
                StokvelPayout.remittance_status == STATUS_PENDING,
                StokvelPayout.quote_id.is_(None),
            )
            .values(remittance_status=STATUS_FAILED, updated_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
    logger.error(
        "event=stokvel.payout_needs_a_person payout_id=%s reason=%s: marked "
        "failed and nothing created",
        payout_id,
        reason,
    )
    return "failed"
