"""Applying the stokvel contract's events to the database (R2-13, #235).

`stokvel.sync_events` (in `stokvel_tasks`) reads the vault's events block range
by block range and hands each one to `apply_event`, inside the same database
transaction that moves the cursor (`StokvelSyncState`). Every handler is
guarded, so applying an event twice changes nothing: a replayed range, or an
event the worker already recorded from a receipt, is a no-op.

- `ContributionMade`: records the contribution as mined through
  `stokvel_ledger.record_mined`, the same guard `confirm_contribution` uses.
  The safety net for a confirmation that was lost.
- `CycleClosed`: closes the cycle (`active -> closed`).
- `RoundFinalised`: only noted for now. Who records a release (the payout row
  and the `STOKVEL -> Treasury` leg) is R3-04's (#241), and its interface is
  still being agreed (doc section 8). `_round_finalised` is where the sync
  will queue it.

Events the database cannot place (a stokvel or cycle it does not have) are
skipped quietly: the contract is shared, so a local or QA backend sees the
other's stokvels too.
"""

import logging

from remitx_api.clock import utcnow
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from sqlalchemy import select, update

from remitx_worker import evm_service
from remitx_worker.stokvel_contract import ContractEvent
from remitx_worker.stokvel_ledger import CONFIRMED, IN_FLIGHT, record_mined

logger = logging.getLogger(__name__)

# What `apply_event` reports, for the task's summary and the tests.
APPLIED = "applied"
ALREADY_RECORDED = "already_recorded"
UNKNOWN = "unknown"
UNMATCHED = "unmatched"
NOTED = "noted"


def apply_event(session, event: ContractEvent) -> str:
    """Apply one vault event in `session`. The caller commits, with the
    cursor."""
    handler = {
        "ContributionMade": _contribution_made,
        "CycleClosed": _cycle_closed,
        "RoundFinalised": _round_finalised,
    }[event.name]
    return handler(session, event)


def _cycle(session, event: ContractEvent) -> StokvelCycle | None:
    """The database cycle an event names: its stokvel (the packed `id`) and
    the contract's 1-based `cycle`, which is `cycle_number`."""
    stokvel_id = evm_service.bytes32_to_uuid(event.args["id"])
    if stokvel_id is None:
        return None
    return session.scalar(
        select(StokvelCycle).where(
            StokvelCycle.stokvel_id == stokvel_id,
            StokvelCycle.cycle_number == event.args["cycle"],
        )
    )


def _skip_unknown(event: ContractEvent) -> str:
    logger.info(
        "event=stokvel.sync_unknown name=%s tx_hash=%s block=%s: not a stokvel "
        "or cycle this database has; skipped",
        event.name,
        event.tx_hash,
        event.block_number,
    )
    return UNKNOWN


def _contribution_made(session, event: ContractEvent) -> str:
    cycle = _cycle(session, event)
    member_id = evm_service.bytes32_to_uuid(event.args["memberId"])
    if cycle is None or member_id is None:
        return _skip_unknown(event)
    rows = session.scalars(
        select(StokvelContribution).where(
            StokvelContribution.cycle_id == cycle.id,
            StokvelContribution.round == event.args["round"],
            StokvelContribution.member_id == member_id,
        )
    ).all()
    # At most one is in flight (uq_stokvel_contributions_once).
    in_flight = next((row for row in rows if row.status in IN_FLIGHT), None)
    if in_flight is not None:
        if in_flight.evm_tx_hash and (
            in_flight.evm_tx_hash.lower() != event.tx_hash.lower()
        ):
            logger.warning(
                "event=stokvel.sync_hash_differs contribution_id=%s stored=%s "
                "event=%s: recording the mined transaction from the event",
                in_flight.id,
                in_flight.evm_tx_hash,
                event.tx_hash,
            )
        if evm_service.to_base_units(in_flight.amount_token) != event.args["amount"]:
            logger.warning(
                "event=stokvel.sync_amount_differs contribution_id=%s "
                "amount_token=%s event_amount=%s",
                in_flight.id,
                in_flight.amount_token,
                event.args["amount"],
            )
        record_mined(session, in_flight.id, event.tx_hash, event.block_number)
        logger.info(
            "event=stokvel.sync_contribution_confirmed contribution_id=%s "
            "tx_hash=%s block=%s",
            in_flight.id,
            event.tx_hash,
            event.block_number,
        )
        return APPLIED
    if any(row.status == CONFIRMED for row in rows):
        return ALREADY_RECORDED
    # Paid on-chain, but the database has it failed or not at all: the
    # books and the chain disagree, which needs a person.
    logger.error(
        "event=stokvel.sync_contribution_unmatched cycle_id=%s round=%s "
        "member_id=%s tx_hash=%s block=%s: the chain has this contribution "
        "but no pending or confirmed row does",
        cycle.id,
        event.args["round"],
        member_id,
        event.tx_hash,
        event.block_number,
    )
    return UNMATCHED


def _cycle_closed(session, event: ContractEvent) -> str:
    cycle = _cycle(session, event)
    if cycle is None:
        return _skip_unknown(event)
    closed = session.execute(
        update(StokvelCycle)
        .where(
            StokvelCycle.id == cycle.id,
            StokvelCycle.status == StokvelCycleStatus.ACTIVE.value,
        )
        .values(status=StokvelCycleStatus.CLOSED.value, closed_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    if closed.rowcount == 1:
        logger.info(
            "event=stokvel.sync_cycle_closed cycle_id=%s tx_hash=%s block=%s",
            cycle.id,
            event.tx_hash,
            event.block_number,
        )
        return APPLIED
    if cycle.status == StokvelCycleStatus.CLOSED.value:
        return ALREADY_RECORDED
    logger.error(
        "event=stokvel.sync_cycle_unmatched cycle_id=%s status=%s tx_hash=%s: "
        "the chain closed a cycle the database has as %s",
        cycle.id,
        cycle.status,
        event.tx_hash,
        cycle.status,
    )
    return UNMATCHED


def _round_finalised(session, event: ContractEvent) -> str:
    """Noted only, until R3-04 (#241) builds `stokvel.release_pool`.

    Proposed interface (doc section 8): queue
    `release_pool(cycle_id, round, tx_hash, block_number)`. It records the
    release that already happened on-chain (the payout row, released, and
    the `STOKVEL -> Treasury` leg) without calling `finalise` again. The
    scheduled release (R3-11, #248) also catches any round left unrecorded.
    """
    cycle = _cycle(session, event)
    if cycle is None:
        return _skip_unknown(event)
    logger.info(
        "event=stokvel.round_finalised cycle_id=%s round=%s pool=%s tx_hash=%s "
        "block=%s: released on-chain; recorded by the release task (R3-04)",
        cycle.id,
        event.args["round"],
        event.args["pool"],
        event.tx_hash,
        event.block_number,
    )
    return NOTED
