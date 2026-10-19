"""Applying the stokvel contract's events to the database (R2-13, #235).

`stokvel.sync_events` (in `stokvel_tasks`) reads the vault's events block range
by block range and hands each one to `apply_event`, inside the transaction that
moves the cursor (`StokvelSyncState`). Every handler is guarded, so applying an
event twice changes nothing: a replayed range, or an event the worker already
recorded from a receipt, is a no-op.

A handler reports one of:

- `APPLIED` / `ALREADY_RECORDED` / `UNKNOWN`: done (for `UNKNOWN`, the
  database has no such stokvel or cycle: the contract is shared, so a local
  or QA backend sees the other's stokvels too)
- `WAITING`: it cannot be applied yet; the task holds it
  (`StokvelHeldEvent`) and retries it on every run
- raises `EventNeedsAPerson` when the chain and the database disagree; the
  task holds it as failed, without changing anything

The events:

- `ContributionMade`: records the contribution as mined through
  `stokvel_ledger.record_mined`, the same guard `confirm_contribution` uses.
  The safety net for a confirmation that was lost.
- `RoundFinalised`: records the release through `stokvel_ledger.record_release`
  (R3-04, #241), the guard `release_pool` shares: the payout becomes
  `released` and the `STOKVEL -> Treasury` leg is booked, once. Rounds held
  as waiting before R3-04 are recorded by the next run.
- `CycleClosed`: closes the cycle (`active -> closed`), but only once every
  round's payout is recorded as released. Until then it waits, so the cycle
  is not closed (and a new one cannot open) with a payout missing.
"""

import logging
from typing import Any

from remitx_api.clock import utcnow
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_payout import (
    StokvelPayout,
    StokvelPayoutReleaseStatus,
)
from sqlalchemy import func, select, update

from remitx_worker import evm_service
from remitx_worker.stokvel_contract import ContractEvent
from remitx_worker.stokvel_ledger import (
    ALREADY_RECORDED as ALREADY_RECORDED_RELEASE,
    CONFIRMED,
    IN_FLIGHT,
    ReleaseConflict,
    record_mined,
    record_release,
)

logger = logging.getLogger(__name__)

# What `apply_event` reports, for the task's summary and the tests.
APPLIED = "applied"
ALREADY_RECORDED = "already_recorded"
UNKNOWN = "unknown"
WAITING = "waiting"


class EventNeedsAPerson(Exception):
    """The event and the database disagree in a way the sync must not guess
    at. Nothing was changed; the task holds the event as failed with this
    message."""


def apply_event(session, event: ContractEvent) -> str:
    """Apply one vault event in `session`. The caller commits, with the
    cursor."""
    handler = {
        "ContributionMade": _contribution_made,
        "CycleClosed": _cycle_closed,
        "RoundFinalised": _round_finalised,
    }[event.name]
    return handler(session, event)


def args_to_json(args: dict[str, Any]) -> dict[str, Any]:
    """An event's arguments in a JSON column: bytes as 0x hex strings. The
    vault's synced events have only `bytes32` and integer arguments, so a
    string is always bytes."""
    return {
        key: "0x" + bytes(value).hex()
        if isinstance(value, bytes | bytearray)
        else value
        for key, value in args.items()
    }


def args_from_json(args: dict[str, Any]) -> dict[str, Any]:
    return {
        key: bytes.fromhex(value[2:]) if isinstance(value, str) else value
        for key, value in args.items()
    }


def _cycle(session, event: ContractEvent) -> StokvelCycle | None:
    """The database cycle an event names: its stokvel (the packed `id`) and
    the contract's 1-based `cycle`, which is `cycle_number` (R2-10 keeps the
    two equal)."""
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
            # The worker sent a different transaction for this contribution
            # than the one the chain recorded: do not move the books onto it.
            raise EventNeedsAPerson(
                f"contribution {in_flight.id} stored {in_flight.evm_tx_hash}, "
                f"but the chain recorded it in {event.tx_hash}"
            )
        if evm_service.to_base_units(in_flight.amount_token) != event.args["amount"]:
            logger.warning(
                "event=stokvel.sync_amount_differs contribution_id=%s "
                "amount_token=%s event_amount=%s",
                in_flight.id,
                in_flight.amount_token,
                event.args["amount"],
            )
        if (
            record_mined(session, in_flight.id, event.tx_hash, event.block_number)
            is None
        ):
            # `confirm_contribution` recorded it in the meantime.
            return ALREADY_RECORDED
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
    # Paid on-chain, but the database has it failed or not at all.
    raise EventNeedsAPerson(
        f"the chain has a contribution for cycle {cycle.id} round "
        f"{event.args['round']} member {member_id} that no pending or "
        "confirmed row matches"
    )


def _cycle_closed(session, event: ContractEvent) -> str:
    cycle = _cycle(session, event)
    if cycle is None:
        return _skip_unknown(event)
    if cycle.status == StokvelCycleStatus.CLOSED.value:
        return ALREADY_RECORDED
    if cycle.status != StokvelCycleStatus.ACTIVE.value:
        raise EventNeedsAPerson(
            f"the chain closed cycle {cycle.id}, which the database has as "
            f"{cycle.status}"
        )
    released = session.scalar(
        select(func.count())
        .select_from(StokvelPayout)
        .where(
            StokvelPayout.cycle_id == cycle.id,
            StokvelPayout.release_status == StokvelPayoutReleaseStatus.RELEASED.value,
        )
    )
    if released < (cycle.total_rounds or 0):
        # The last round's RoundFinalised comes just before this in the same
        # transaction and is normally recorded by now. It is not if it was
        # held (a contribution in its pool not yet recorded, say): closing
        # now would leave its payout unrecorded and let a new cycle open.
        logger.info(
            "event=stokvel.sync_cycle_close_waiting cycle_id=%s released=%s of %s",
            cycle.id,
            released,
            cycle.total_rounds,
        )
        return WAITING
    session.execute(
        update(StokvelCycle)
        .where(
            StokvelCycle.id == cycle.id,
            StokvelCycle.status == StokvelCycleStatus.ACTIVE.value,
        )
        .values(status=StokvelCycleStatus.CLOSED.value, closed_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    logger.info(
        "event=stokvel.sync_cycle_closed cycle_id=%s tx_hash=%s block=%s",
        cycle.id,
        event.tx_hash,
        event.block_number,
    )
    return APPLIED


def _round_finalised(session, event: ContractEvent) -> str:
    """Record the release in this transaction through
    `stokvel_ledger.record_release` (R3-04, #241), the guard
    `release_pool` shares: the payout row (created if missing) becomes
    `released` and the `STOKVEL -> Treasury` leg is booked, once.

    Recorded here rather than queued, so a cycle's last `RoundFinalised` is
    recorded before the `CycleClosed` that follows it in the same transaction,
    and the cycle closes in the same run. Events held as waiting before R3-04
    are replayed by the next run.

    The `STOKVEL` balance cannot go below zero: if a contribution in the pool
    is not recorded yet, recording fails and the event is held as failed,
    then retried on the next run, once the contribution is in.
    """
    cycle = _cycle(session, event)
    member_id = evm_service.bytes32_to_uuid(event.args["memberId"])
    if cycle is None or member_id is None:
        return _skip_unknown(event)
    try:
        outcome = record_release(
            session,
            cycle_id=cycle.id,
            round_=event.args["round"],
            member_id=member_id,
            pool=evm_service.from_base_units(event.args["pool"]),
            tx_hash=event.tx_hash,
            block_number=event.block_number,
        )
    except ReleaseConflict as exc:
        raise EventNeedsAPerson(str(exc)) from exc
    if outcome == ALREADY_RECORDED_RELEASE:
        return ALREADY_RECORDED
    logger.info(
        "event=stokvel.sync_round_released cycle_id=%s round=%s tx_hash=%s block=%s",
        cycle.id,
        event.args["round"],
        event.tx_hash,
        event.block_number,
    )
    return APPLIED
