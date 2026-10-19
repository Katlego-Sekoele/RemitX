"""Recording a stokvel's on-chain outcomes in the ledger.

Each outcome is recorded through one guard, whichever part of the worker sees
it first:

- a mined contribution (`record_mined`): `stokvel_tasks.confirm_contribution`
  after a receipt, or the event sync (`stokvel_sync`) from `ContributionMade`
- a released pool (`record_release`, R3-04): the event sync from
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

# What `record_release` reports.
RECORDED = "recorded"
ALREADY_RECORDED = "already_recorded"


class ReleaseConflict(Exception):
    """A release on-chain and the database disagree in a way the worker must
    not guess at: the round pays a different member, it is recorded with a
    different hash, or a person has marked it failed. Raised before anything
    is written."""


def contribution_legs(contribution: StokvelContribution) -> list[uuid.UUID]:
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
    # (transaction.py). Destinations first, as in settlement.
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
    """The cycle member round `round_` pays: the one whose payout position is
    the round. None if the round pays nobody in this cycle."""
    return session.scalar(
        select(StokvelCycleMember.member_id).where(
            StokvelCycleMember.cycle_id == cycle_id,
            StokvelCycleMember.payout_position == round_,
        )
    )


def ensure_payout(session, cycle_id: uuid.UUID, round_: int) -> StokvelPayout:
    """The round's payout row, created `pending` for its scheduled member if
    there is none yet. The release owns payout creation: a round released
    inside a `contribute` has had no row until it is recorded.

    Two workers can create it at once (the event sync and `release_pool` on
    the same round). The insert runs in a savepoint; if it fails and the row
    now exists, the other worker made it and that row is returned. Any other
    failure is raised. Raises `ReleaseConflict` if the round pays no member.
    """
    existing = _payout(session, cycle_id, round_)
    if existing is not None:
        return existing
    member_id = scheduled_member(session, cycle_id, round_)
    if member_id is None:
        raise ReleaseConflict(
            f"cycle {cycle_id} has no member in payout position {round_}"
        )
    savepoint = session.begin_nested()
    try:
        session.add(StokvelPayout(cycle_id=cycle_id, round=round_, member_id=member_id))
        session.flush()
    except IntegrityError:
        savepoint.rollback()
        existing = _payout(session, cycle_id, round_)
        if existing is None:
            raise
        return existing
    savepoint.commit()
    return _payout(session, cycle_id, round_)


def _payout(session, cycle_id: uuid.UUID, round_: int) -> StokvelPayout | None:
    return session.scalar(
        select(StokvelPayout)
        .where(StokvelPayout.cycle_id == cycle_id, StokvelPayout.round == round_)
        .execution_options(populate_existing=True)
    )


def record_release(
    session,
    *,
    cycle_id: uuid.UUID,
    round_: int,
    member_id: uuid.UUID,
    pool: Decimal,
    tx_hash: str,
    block_number: int,
) -> str:
    """Record a pool the contract released (`RoundFinalised`) in `session`:
    the round's payout becomes `released` with the release's hash and block,
    and the `stokvel_pool_release` leg moves `pool` UCTUSD from the stokvel's
    `STOKVEL` account to the Treasury Wallet, confirmed at once, since it is
    already mined (doc section 3: the `STOKVEL` balance always equals the
    stokvel's unreleased pools in the contract).

    The payout row is created if missing (`ensure_payout`). Guarded on it
    being `pending` or `processing`, so it happens once whoever calls it: the
    event sync from the event, or `release_pool` from its receipt. Only the
    caller whose guarded update succeeds books the leg; the leg is written in
    a savepoint that is rolled back if the update matches nothing.

    The hash given wins over one `release_pool` stored: the contract releases
    a round once, so if a `contribute` released it before our `finalise` was
    mined, the release is the `contribute`'s and our transaction reverts.

    Returns `RECORDED`, or `ALREADY_RECORDED` if the round is already
    released with this hash. Raises `ReleaseConflict`, before writing
    anything, if the round pays a different member, is released with another
    hash, or is `failed`. The caller commits.

    The payout itself (quote, remittance, settlement) is R3-05 and R3-06: it
    pays from the Treasury Wallet to the beneficiary, so the pool does not
    pass back through `STOKVEL`, and `remittance_status` stays `pending` here.
    """
    # Checked before the row is created, so a conflict writes nothing.
    scheduled = scheduled_member(session, cycle_id, round_)
    if scheduled is not None and scheduled != member_id:
        raise ReleaseConflict(
            f"round {round_} of cycle {cycle_id} pays member {scheduled}, "
            f"but the chain released it to {member_id}"
        )
    payout = ensure_payout(session, cycle_id, round_)
    if payout.member_id != member_id:
        raise ReleaseConflict(
            f"round {round_} of cycle {cycle_id} pays member {payout.member_id}, "
            f"but the chain released it to {member_id}"
        )
    if payout.release_status not in RELEASE_IN_FLIGHT:
        return _already_released(payout, tx_hash)

    stokvel_account_id, treasury_id, expected = _release_accounts(session, cycle_id)
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
    savepoint = session.begin_nested()
    leg = Transaction(
        tx_id=uuid.uuid4(),
        type=TYPE_STOKVEL_POOL_RELEASE,
        credit_account_id=stokvel_account_id,
        debit_account_id=treasury_id,
        amount=pool,
        currency=CURRENCY_TOKEN,
        status=TX_STATUS_CONFIRMED,
        processed_at=now,
        confirmed_at=now,
    )
    try:
        session.add(leg)
        session.flush()
        outcome = _release(session, payout, leg, tx_hash, block_number, now)
        if outcome == RECORDED:
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
    """The guarded `pending|processing -> released`. `RECORDED` if this caller
    made it, None if the payout had left those statuses meanwhile."""
    released = session.execute(
        update(StokvelPayout)
        .where(
            StokvelPayout.id == payout.id,
            StokvelPayout.release_status.in_(RELEASE_IN_FLIGHT),
        )
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
    # `debit_account_id` is the destination, `credit_account_id` the source
    # (transaction.py). Destination first, as in `record_mined`. The
    # `STOKVEL` balance can never go below zero (accounts_stokvel_balance_
    # nonneg): if a contribution in this pool is not recorded yet, this
    # raises and the caller leaves the release to be recorded later.
    session.execute(
        update(Account)
        .where(Account.account_id == treasury_id)
        .values(account_balance=Account.account_balance + pool)
    )
    session.execute(
        update(Account)
        .where(Account.account_id == stokvel_account_id)
        .values(account_balance=Account.account_balance - pool)
    )
    session.flush()


def _already_released(payout: StokvelPayout, tx_hash: str) -> str:
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
    """(the stokvel's `STOKVEL` account, the Treasury Wallet's UCTUSD
    account, the pool the cycle should release: the contribution times the
    number of rounds, or None if the cycle has no round count)."""
    stokvel, total_rounds = session.execute(
        select(Stokvel, StokvelCycle.total_rounds)
        .join(StokvelCycle, StokvelCycle.stokvel_id == Stokvel.id)
        .where(StokvelCycle.id == cycle_id)
    ).one()
    if stokvel.account_id is None:
        # Created with the stokvel (R2-07); never missing once in service.
        raise RuntimeError(f"stokvel {stokvel.id} has no STOKVEL account")
    treasury_id = session.scalar(
        select(Account.account_id).where(
            Account.type == TYPE_EVM_WALLET,
            Account.account_currency == CURRENCY_TOKEN,
        )
    )
    if treasury_id is None:
        # Seeded by migration: a missing one is a deployment fault.
        raise RuntimeError(f"no {TYPE_EVM_WALLET} account in {CURRENCY_TOKEN}")
    expected = (
        None if total_rounds is None else stokvel.contribution_amount * total_rounds
    )
    return stokvel.account_id, treasury_id, expected
