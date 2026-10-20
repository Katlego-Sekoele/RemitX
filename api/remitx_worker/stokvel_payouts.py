"""Paying a released stokvel pool out to the beneficiary (R3-05, #242; doc
section 4).

Once a round's release is recorded (R3-04, `stokvel_ledger.record_pool_release`),
the pool is in the Treasury Wallet. `stokvel.settle_payout(payout_id)` turns
it into a normal remittance (D6), with the stokvel as the quote's sender and
the scheduled member's chosen Payout beneficiary as the recipient:

- one quote, priced by `quote_service.price_stokvel_payout`: the full pool,
  no fee or margin (the members paid the fee on top of their contributions),
  and no sending limits (D8). It is accepted at once (`USED`): there is no
  customer to accept it
- its pending legs, sharing the quote's `quote_id` as settlement expects. The
  pool is paid from the Treasury Wallet, where the release put it, not back
  through `STOKVEL` (decided 2026-10-19, #241):

      Treasury -> beneficiary token         remittance (the remittance's leg)
      beneficiary token -> Treasury         remittance
      Treasury -> token issuer              token_burn
      RemitX bank -> beneficiary fiat       beneficiary_payout

  No fiat comes in and no fee is taken, so a user remittance's first three
  legs have no counterpart here
- one remittance, and the payout's `remittance_status` `pending ->
  processing` with its `quote_id` and `remittance_id`, in the same commit

Handing the remittance to the settlement chain (`settle_remittance`, the
burn) and finishing the payout are R3-06 (#243).

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
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PROCESSING,
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_REMITTANCE,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.services import exchange_rate_service, queue_service, quote_service
from sqlalchemy import or_, select, update

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
    """Queue `stokvel.settle_payout` for released payouts whose remittance has
    not started. Run by the event sync after each run, so a release recorded
    by the sync or by `release_pool` is paid out within one sync interval, and
    a lost message is queued again. Returns how many were queued.

    `updated_at` marks when a payout was last queued. A payout is due once,
    as soon as it is released (`record_pool_release` sets `updated_at` and
    `released_at` together), then again only `REQUEUE_AFTER` after it was
    last queued, so a busy worker is not sent a pile of copies. The longest
    waiting go first, so a few that keep failing cannot keep the rest out.
    """
    now = datetime.now(UTC)
    due = (
        StokvelPayout.release_status == RELEASED,
        StokvelPayout.remittance_status == STATUS_PENDING,
        StokvelPayout.quote_id.is_(None),
        or_(
            StokvelPayout.updated_at <= StokvelPayout.released_at,
            StokvelPayout.updated_at < now - REQUEUE_AFTER,
        ),
    )
    with session_scope() as session:
        payout_ids = session.scalars(
            select(StokvelPayout.id)
            .where(*due)
            .order_by(StokvelPayout.updated_at)
            .limit(_QUEUE_LIMIT)
        ).all()
        if payout_ids:
            session.execute(
                update(StokvelPayout)
                .where(StokvelPayout.id.in_(payout_ids), *due)
                .values(updated_at=now)
                .execution_options(synchronize_session=False)
            )
    for payout_id in payout_ids:
        queue_service.enqueue_settle_payout(str(payout_id))
    return len(payout_ids)


@celery.task(name="stokvel.settle_payout")
def settle_payout(payout_id: str) -> str:
    """Create a released payout's quote, legs and remittance (module
    docstring). Reports what happened, for the log and the tests."""
    try:
        target_id = uuid.UUID(payout_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("payout id %r is not a valid id; skipping", payout_id)
        return "skipped"

    with session_scope() as session:
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

    if problem is not None:
        return _fail(target_id, problem)

    try:
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
        return _fail(target_id, str(exc))

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
    return "created"


def _beneficiary_problem(session, member, beneficiary) -> str | None:
    """Why the member's chosen beneficiary cannot be paid now, or None. The
    payout currency was copied from the beneficiary when it was chosen
    (R2-09, #231); if they differ now, the member's choice is not what would
    be paid, so a person decides."""
    if member.payout_beneficiary_id is None or member.payout_currency is None:
        return "the member has no payout beneficiary"
    if beneficiary is None:
        return f"beneficiary {member.payout_beneficiary_id} no longer exists"
    if beneficiary.payout_currency != member.payout_currency:
        return (
            f"beneficiary {beneficiary.beneficiary_id} is now paid in "
            f"{beneficiary.payout_currency}, but the member chose it for "
            f"{member.payout_currency}"
        )
    for currency in (CURRENCY_TOKEN, member.payout_currency):
        if _user_account(session, beneficiary.linked_user_id, currency) is None:
            return (
                f"the beneficiary's user {beneficiary.linked_user_id} has no "
                f"{currency} account to credit"
            )
    return None


def _price(pool, stokvel_currency: str, payout_currency: str):
    """`price_stokvel_payout` on a session of its own, bound as the API's
    request session, which the rate service reads and may write a fetched
    rate through. Its own commit, so no lock is held while a rate is
    fetched."""
    with session_scope() as session:
        token = set_request_db_session(session)
        try:
            return quote_service.price_stokvel_payout(
                pool, stokvel_currency, payout_currency
            )
        finally:
            reset_request_db_session(token)


def _create_remittance(
    session, payout_id, *, stokvel_id, recipient_id, pricing, sender_amount
) -> Remittance:
    now = datetime.now(UTC)
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

    def leg(type_, source, destination, amount, currency) -> Transaction:
        # `credit_account_id` is the source, `debit_account_id` the
        # destination (transaction.py).
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
    paid_out = leg(TYPE_REMITTANCE, treasury, beneficiary_token, tokens, CURRENCY_TOKEN)
    leg(TYPE_REMITTANCE, beneficiary_token, treasury, tokens, CURRENCY_TOKEN)
    leg(TYPE_TOKEN_BURN, treasury, issuer, tokens, CURRENCY_TOKEN)
    leg(
        TYPE_BENEFICIARY_PAYOUT,
        bank,
        beneficiary_fiat,
        pricing.receiver_amount,
        pricing.receiver_payout_currency,
    )
    session.flush()
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
    return session.scalar(
        select(Account.account_id).where(
            Account.user_id == user_id,
            Account.account_currency == currency,
        )
    )


def _fail(payout_id: uuid.UUID, reason: str) -> str:
    """`pending -> failed`, with nothing created, for a person to resolve."""
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
        "event=stokvel.payout_needs_a_person payout_id=%s: %s; marked failed "
        "and nothing created",
        payout_id,
        reason,
    )
    return "failed"
