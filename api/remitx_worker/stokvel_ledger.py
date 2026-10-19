"""Recording a stokvel contribution's on-chain outcome in the ledger.

Shared by `stokvel_tasks.confirm_contribution` (after a receipt) and the
event sync (`stokvel_sync`, from a `ContributionMade` event), so a mined
contribution is recorded through one guard, whichever sees it first.
"""

import uuid

from remitx_api.clock import utcnow
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED as TX_STATUS_CONFIRMED,
    STATUS_PENDING as TX_STATUS_PENDING,
    STATUS_PROCESSING as TX_STATUS_PROCESSING,
    Transaction,
)
from sqlalchemy import select, update

CONFIRMED = StokvelContributionStatus.CONFIRMED.value
IN_FLIGHT = (
    StokvelContributionStatus.PENDING.value,
    StokvelContributionStatus.PROCESSING.value,
)
LEGS_IN_FLIGHT = (TX_STATUS_PENDING, TX_STATUS_PROCESSING)


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
