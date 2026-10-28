"""Recording a stokvel's on-chain outcomes in the ledger.

Each outcome is recorded through one guard, whichever part of the worker sees
it first:

- a mined contribution (`record_mined`): `stokvel_tasks.confirm_contribution`
  after a receipt, or the event sync (`stokvel_sync`) from `ContributionMade`
- a released pool (`record_pool_release`): the event sync from
  `RoundFinalised`, or `stokvel_release.release_pool` after the receipt of
  the `finalise` it sent
"""

import logging
import uuid
from decimal import Decimal

from remitx_api.clock import utcnow
from remitx_api.models.orm.account import CURRENCY_TOKEN, TYPE_EVM_WALLET, Account
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_payout import (
    StokvelPayout,
    StokvelPayoutReleaseStatus,
)
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED as TX_STATUS_CONFIRMED,
    STATUS_PENDING as TX_STATUS_PENDING,
    STATUS_PROCESSING as TX_STATUS_PROCESSING,
    TYPE_STOKVEL_POOL_RELEASE,
    Transaction,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

CONFIRMED = StokvelContributionStatus.CONFIRMED.value
IN_FLIGHT = (
    StokvelContributionStatus.PENDING.value,
    StokvelContributionStatus.PROCESSING.value,
)
LEGS_IN_FLIGHT = (TX_STATUS_PENDING, TX_STATUS_PROCESSING)

RELEASE_PENDING = StokvelPayoutReleaseStatus.PENDING.value
RELEASE_PROCESSING = StokvelPayoutReleaseStatus.PROCESSING.value
RELEASED = StokvelPayoutReleaseStatus.RELEASED.value
RELEASE_IN_FLIGHT = (RELEASE_PENDING, RELEASE_PROCESSING)

# What `record_pool_release` reports.
RECORDED = "recorded"
ALREADY_RECORDED = "already_recorded"


class ReleaseConflict(Exception):
    """A release on-chain and the database disagree in a way the worker must
    not guess at. Raised before anything is written."""


def contribution_legs(contribution: StokvelContribution) -> list[uuid.UUID]:
    """The transaction legs of a contribution"""
    return [
        tx_id
        for tx_id in (
            contribution.fiat_tx_id,
            contribution.token_tx_id,
            contribution.fee_tx_id,
        )
        if tx_id is not None
    ]


def record_mined(
    session, contribution_id: uuid.UUID, tx_hash: str, block_number: int
) -> int | None:
    """Record a mined `contribute` in `session`: the contribution and its legs
    become `confirmed` and the legs move their balances (the member's fiat to
    RemitX's bank, UCTUSD from the Treasury to the stokvel's `STOKVEL`
    account, the fee to fee revenue).

    Guarded on the contribution still being `pending` or `processing`, so it
    happens once whoever calls it: `confirm_contribution` after the receipt,
    or the event sync (R2-13, #235) from a `ContributionMade` event. Returns
    the number of legs settled, or None if the contribution was not in
    flight (already recorded, failed, or unknown) and nothing changed. The
    caller commits.
    """
    changed = session.execute(
        update(StokvelContribution)
        .where(
            StokvelContribution.id == contribution_id,
            StokvelContribution.status.in_(IN_FLIGHT),
        )
        .values(
            status=CONFIRMED,
            evm_tx_hash=tx_hash,
            block_number=block_number,
            confirmed_at=utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount == 0:
        return None
    leg_ids = contribution_legs(session.get(StokvelContribution, contribution_id))
    session.execute(
        update(Transaction)
        .where(
            Transaction.tx_id.in_(leg_ids),
            Transaction.status.in_(LEGS_IN_FLIGHT),
        )
        .values(status=TX_STATUS_CONFIRMED, confirmed_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    legs = session.execute(
        select(
            Transaction.credit_account_id,
            Transaction.debit_account_id,
            Transaction.amount,
        ).where(Transaction.tx_id.in_(leg_ids))
    ).all()
    # `debit_account_id` is the destination, `credit_account_id` the source
    # (transaction.py). Destinations first, as in settlement. That takes the
    # `STOKVEL` row lock before the Treasury's, the order `_move_pool` keeps.
    for _source, destination, amount in legs:
        session.execute(
            update(Account)
            .where(Account.account_id == destination)
            .values(account_balance=Account.account_balance + amount)
        )
    for source, _destination, amount in legs:
        session.execute(
            update(Account)
            .where(Account.account_id == source)
            .values(account_balance=Account.account_balance - amount)
        )
    return len(legs)


def scheduled_member(session, cycle_id: uuid.UUID, round_: int) -> uuid.UUID | None:
    """Looks in the cycle's member list for the member whose payout_position
    equals the round number and returns that member's ID. If nobody holds that
    position, it returns None"""
    return session.scalar(
        select(StokvelCycleMember.member_id).where(
            StokvelCycleMember.cycle_id == cycle_id,
            StokvelCycleMember.payout_position == round_,
        )
    )


def ensure_payout(session, cycle_id: uuid.UUID, round_: int) -> StokvelPayout:
    """Get the round's payout row, creating it as `pending` if it does not
    exist yet. A round released by a `contribute` has no payout row until its
    release is recorded, so the release creates it.

    The event sync and `release_pool` can both try to create the row at once.
    If an insert fails because the other got there first, its row is
    returned. Raises `ReleaseConflict` if no member is scheduled for the round.
    """
    # Check if the payout already exists
    existing = _payout(session, cycle_id, round_)
    if existing is not None:
        return existing
    # Check if a member is scheduled for the round
    member_id = scheduled_member(session, cycle_id, round_)
    if member_id is None:
        raise ReleaseConflict(
            f"cycle {cycle_id} has no member in payout position {round_}"
        )
    # Create a savepoint to allow rollback if the insert fails
    savepoint = session.begin_nested()
    # Try to create the payout row
    try:
        session.add(StokvelPayout(cycle_id=cycle_id, round=round_, member_id=member_id))
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        # If the insert fails, check if another worker created the row first.
        existing = _payout(session, cycle_id, round_)
        if existing is None:
            raise
        # Return the existing row if it was created by another worker
        return existing
    savepoint.commit()
    # Return the newly created payout row
    return _payout(session, cycle_id, round_)


def _payout(session, cycle_id: uuid.UUID, round_: int) -> StokvelPayout | None:
    """Get the round's payout row, or None if it does not exist yet. Does not
    create it."""
    return session.scalar(
        select(StokvelPayout)
        .where(StokvelPayout.cycle_id == cycle_id, StokvelPayout.round == round_)
        .execution_options(populate_existing=True)
    )


def record_pool_release(
    session,
    *,
    cycle_id: uuid.UUID,
    round_: int,
    member_id: uuid.UUID,
    pool: Decimal,
    tx_hash: str,
    block_number: int,
) -> str:
    """Record a round the contract released: mark its payout `released` and
    move pool amount from the stokvel's `STOKVEL` account to the Treasury.

    Called by the event sync and by `release_pool`. Only the first call
    records it; a later one gets `ALREADY_RECORDED`. Raises
    `ReleaseConflict`, writing nothing, if the chain's release does not match
    the database. The caller commits.

    The member is paid later, from the Treasury, by `settle_payout`.
    """
    # Checked a member is scheduled for the round
    scheduled = scheduled_member(session, cycle_id, round_)
    if scheduled is not None and scheduled != member_id:
        raise ReleaseConflict(
            f"round {round_} of cycle {cycle_id} pays member {scheduled}, "
            f"but the chain released it to {member_id}"
        )
    # Check the payout row exists (or create it) and that it is for the right member
    payout = ensure_payout(session, cycle_id, round_)
    if payout.member_id != member_id:
        raise ReleaseConflict(
            f"round {round_} of cycle {cycle_id} pays member {payout.member_id}, "
            f"but the chain released it to {member_id}"
        )
    # If the payout is already released, check the chain's release matches the
    # database
    if payout.release_status not in RELEASE_IN_FLIGHT:
        return _already_released(payout, tx_hash)
    # Get the accounts the release moves between and the expected pool amount.
    stokvel_account_id, treasury_id, expected = _release_accounts(session, cycle_id)
    # If the pool amount differs from the expected, log a warning but continue
    # to record the release.
    if expected is not None and pool != expected:
        logger.warning(
            "event=stokvel.release_amount_differs cycle_id=%s round=%s "
            "pool=%s expected=%s: booking the chain's amount",
            cycle_id,
            round_,
            pool,
            expected,
        )

    now = utcnow()
    # Create a savepoint to allow rollback if the update fails
    savepoint = session.begin_nested()

    # Create a transaction leg for the pool release
    leg = Transaction(
        tx_id=uuid.uuid4(),
        type=TYPE_STOKVEL_POOL_RELEASE,
        credit_account_id=stokvel_account_id,  # From the stokvel's STOKVEL account
        debit_account_id=treasury_id,  # to the Treasury Wallet's UCTUSD account
        amount=pool,  # amount released from the pool in UCTUSD
        currency=CURRENCY_TOKEN,
        # Confirmed, since the release has been mined on-chain
        status=TX_STATUS_CONFIRMED,
        processed_at=now,
        confirmed_at=now,
    )
    try:
        session.add(leg)
        session.flush()
        # Check if the payout is still pending or processing, and mark it as
        # released if so. If another worker has already recorded the release,
        # this will return None.
        outcome = _release(session, payout, leg, tx_hash, block_number, now)
        if outcome == RECORDED:
            # Move the pool from the stokvel's STOKVEL account to the Treasury
            # Wallet's UCTUSD account
            _move_pool(session, stokvel_account_id, treasury_id, pool)
    except Exception:
        savepoint.rollback()
        raise
    if outcome != RECORDED:
        # Recorded by another worker between the read and the update.
        savepoint.rollback()
        return _already_released(_payout(session, cycle_id, round_), tx_hash)
    savepoint.commit()
    return RECORDED


def _release(session, payout, leg, tx_hash, block_number, now) -> str | None:
    """Mark the payout `released` if it is still `pending` or `processing`.
    Returns `RECORDED` if this call changed it, or None if another worker
    recorded it first."""
    released = session.execute(
        update(StokvelPayout)
        .where(
            StokvelPayout.id == payout.id,
            # Pending or processing
            StokvelPayout.release_status.in_(RELEASE_IN_FLIGHT),
        )
        # Add the release transaction leg data to the payout row
        .values(
            release_status=RELEASED,
            release_tx_hash=tx_hash,
            release_block_number=block_number,
            release_tx_id=leg.tx_id,
            released_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    return RECORDED if released.rowcount == 1 else None


def _move_pool(session, stokvel_account_id, treasury_id, pool: Decimal) -> None:
    """Move `pool` from the stokvel's `STOKVEL` account to the Treasury
    (updates both account balances).

    `STOKVEL` account balance is updated before the Treasury, the same order
    `record_mined` locks these two rows in.

    `STOKVEL` can never go below zero (accounts_stokvel_balance_nonneg).
    """
    session.execute(
        update(Account)
        .where(Account.account_id == stokvel_account_id)
        .values(account_balance=Account.account_balance - pool)
    )
    session.execute(
        update(Account)
        .where(Account.account_id == treasury_id)
        .values(account_balance=Account.account_balance + pool)
    )
    session.flush()


def _already_released(payout: StokvelPayout, tx_hash: str) -> str:
    """Check if the chain's release matches the database. Returns
    `ALREADY_RECORDED` if it does, or raises `ReleaseConflict` if it does not."""
    if payout.release_status == RELEASED and (
        (payout.release_tx_hash or "").lower() == tx_hash.lower()
    ):
        return ALREADY_RECORDED
    raise ReleaseConflict(
        f"payout {payout.id} is {payout.release_status} with release hash "
        f"{payout.release_tx_hash}, but the chain released it in {tx_hash}"
    )


def _release_accounts(
    session, cycle_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, Decimal | None]:
    """The accounts a release moves between, and the pool expected:

    - the stokvel's `STOKVEL` account
    - the Treasury Wallet's UCTUSD account
    - the expected pool (contribution amount times the number of rounds), or
      None if the cycle has no round count
    """
    # Get the stokvel's `STOKVEL` account and the cycle's total rounds.
    stokvel, total_rounds = session.execute(
        select(Stokvel, StokvelCycle.total_rounds)
        .join(StokvelCycle, StokvelCycle.stokvel_id == Stokvel.id)
        .where(StokvelCycle.id == cycle_id)
    ).one()
    # Check the stokvel has a `STOKVEL` account and the Treasury Wallet's UCTUSD
    # account exists.
    if stokvel.account_id is None:
        # Every stokvel gets one when it is created, so this should not happen.
        raise RuntimeError(f"stokvel {stokvel.id} has no STOKVEL account")
    treasury_id = treasury_account_id(session)
    expected = (
        None if total_rounds is None else stokvel.contribution_amount * total_rounds
    )
    # Return the accounts and the expected pool amount.
    return stokvel.account_id, treasury_id, expected


def treasury_account_id(session) -> uuid.UUID:
    """The Treasury Wallet's UCTUSD ledger account: where a released pool goes
    and where a stokvel's payout is paid from."""
    treasury_id = session.scalar(
        select(Account.account_id).where(
            Account.type == TYPE_EVM_WALLET,
            Account.account_currency == CURRENCY_TOKEN,
        )
    )
    if treasury_id is None:
        # Seeded by migration: a missing one is a deployment fault.
        raise RuntimeError(f"no {TYPE_EVM_WALLET} account in {CURRENCY_TOKEN}")
    return treasury_id
