"""Releasing a stokvel round's pool on-chain.

Most rounds release themselves: the `contribute` that completes a round
releases it in the same transaction, and the event sync records it.

A round that was fully paid before its payout time (always true of a
cycle's last round, if paid on time) has no later contribution to release
it, so someone must call the contract's `finalise`. `release_pool` does
that. It is queued by `release_due_rounds` (at the end of this module, run on
a schedule) and by the Administrator, never by the sync.

Either way the release is recorded with `stokvel_ledger.record_pool_release`,
so it is booked once, by whichever sees it first.

Like contributions, sending is safe to repeat:

- only the call that claims the payout (`pending -> processing`) sends
- the hash is saved before sending, so a retry waits on it instead of
  sending a second `finalise`
- if the contract would refuse, nothing is sent and the claim is given back
  (`processing -> pending`) for a later try
- once a hash may have reached the chain, it is only ever waited on
"""

import logging
import uuid
from datetime import datetime, timedelta

from remitx_api.clock import utcnow
from remitx_api.config import Config
from remitx_api.models.orm.stokvel_contribution import (
    STATUS_CONFIRMED as CONTRIBUTION_CONFIRMED,
    StokvelContribution,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.services import queue_service
from sqlalchemy import and_, func, select, update

from remitx_worker import evm_service, stokvel_contract
from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope
from remitx_worker.stokvel_ledger import (
    RELEASE_PENDING,
    RELEASE_PROCESSING,
    RELEASED,
    ReleaseConflict,
    ensure_payout,
    record_pool_release,
)

logger = logging.getLogger(__name__)

RECEIPT_TIMEOUT_SECONDS = 120
RETRY_SECONDS = 60
MAX_RETRIES = 10

# The round is already released or is not due yet. Nothing to retry.
_NOTHING_TO_DO = frozenset({"AlreadyFinalised", "NotYetFinalisable"})

# The platform's to fix, as for contributions: the contract is paused, the
# Treasury lacks OPERATOR_ROLE, or the token transfer failed. Retried.
_RETRYABLE_REFUSALS = frozenset(
    {"EnforcedPause", "AccessControlUnauthorizedAccount", "SafeERC20FailedOperation"}
)


class _HashNotRecorded(Exception):
    """The signed `finalise`'s hash could not be saved (the payout changed in
    the meantime), so the transaction is not sent."""


@celery.task(bind=True, name="stokvel.release_pool", max_retries=MAX_RETRIES)
def release_pool(self, cycle_id: str, round_: int) -> str:
    """Release a due round's pool by sending `finalise`, then record it.

    1. Get the round's payout row (created if missing) and claim it,
       `pending -> processing`.
    2. Save the transaction hash before sending, so a retry waits on it
       instead of sending a second `finalise`.
    3. Send `finalise` and wait for the receipt.
    4. Record the release from the receipt's `RoundFinalised` event.

    If the payout is already claimed, this never sends (see `_resume`).
    Returns a short word saying what happened, for the logs and tests.
    """
    # Try get the cycle id, if not valid skip the release
    try:
        target_id = uuid.UUID(cycle_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("cycle id %r is not a valid id; skipping", cycle_id)
        return "skipped"
    # Try get the payout row and claim it, if not valid skip the release
    with session_scope() as session:
        stokvel_id = session.scalar(
            select(StokvelCycle.stokvel_id).where(StokvelCycle.id == target_id)
        )
        if stokvel_id is None:
            logger.info("cycle %s does not exist; skipping", cycle_id)
            return "skipped"
        try:
            # get the payout row for the cycle and round, creating it if missing
            payout = ensure_payout(session, target_id, round_)
        # No member is scheduled for this round, so there is no one to pay. Skip.
        except ReleaseConflict as exc:
            logger.error(
                "event=stokvel.release_unscheduled cycle_id=%s round=%s: %s",
                cycle_id,
                round_,
                exc,
            )
            return "skipped"
        # Claim the payout row, `pending -> processing`.
        claimed = session.execute(
            update(StokvelPayout)
            .where(
                StokvelPayout.id == payout.id,
                StokvelPayout.release_status == RELEASE_PENDING,
            )
            .values(release_status=RELEASE_PROCESSING, updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        # If the claim failed, the payout is already claimed. Refresh it to get
        # its status and hash.
        if claimed.rowcount == 0:
            session.refresh(payout)
            status, tx_hash = payout.release_status, payout.release_tx_hash
        payout_id = payout.id

    if claimed.rowcount == 0:
        return _resume(self, payout_id, status, tx_hash)

    recorded: list[str] = []

    def record(tx_hash: str) -> None:
        """Record the signed `finalise`'s hash in the payout row, so a retry
        waits on it instead of sending a second `finalise`. Only called once,
        by the `on_signed` callback. Raises `_HashNotRecorded` if the payout
        changed since the claim (e.g. the sync already recorded it)."""
        with session_scope() as session:
            stored = session.execute(
                update(StokvelPayout)
                .where(
                    StokvelPayout.id == payout_id,
                    StokvelPayout.release_status == RELEASE_PROCESSING,
                    StokvelPayout.release_tx_hash.is_(None),
                )
                .values(release_tx_hash=tx_hash, updated_at=utcnow())
                .execution_options(synchronize_session=False)
            )
        if stored.rowcount != 1:
            raise _HashNotRecorded(tx_hash)
        recorded.append(tx_hash)

    # Try send the signed `finalise` and wait for the receipt.
    # If it fails, give the claim back (`processing -> pending`) for a later try.
    try:
        w3 = evm_service.get_web3()
        tx_hash = stokvel_contract.finalise(stokvel_id, round_, on_signed=record, w3=w3)
    except _HashNotRecorded as exc:
        # The payout changed since the claim (e.g. the sync already recorded
        # it). Nothing was sent.
        logger.warning(
            "event=stokvel.release_not_recorded payout_id=%s tx_hash=%s: no "
            "longer processing without a hash, so the signed finalise was not sent",
            payout_id,
            exc,
        )
        return "skipped"
    except stokvel_contract.ContractRefused as exc:
        _hand_back(payout_id)
        if exc.error in _NOTHING_TO_DO:
            logger.info(
                "event=stokvel.release_not_needed payout_id=%s error=%s: nothing sent",
                payout_id,
                exc.error,
            )
            return "already_released" if exc.error == "AlreadyFinalised" else "not_due"
        if exc.error in _RETRYABLE_REFUSALS:
            return _retry(self, payout_id, exc)
        logger.error(
            "event=stokvel.release_refused payout_id=%s error=%s: the contract "
            "would revert, so nothing was sent",
            payout_id,
            exc.error or exc,
        )
        return "refused"
    except evm_service.TransactionRejected as exc:
        # The RPC refused the transaction, so it can never be mined. Clear
        # its hash along with the claim.
        _hand_back(payout_id, recorded[0] if recorded else None)
        return _retry(self, payout_id, exc)
    except Exception as exc:
        if not recorded:
            # Nothing was signed, so nothing reached the chain.
            _hand_back(payout_id)
            return _retry(self, payout_id, exc)
        (tx_hash,) = recorded
        logger.warning(
            "event=stokvel.release_send_uncertain payout_id=%s tx_hash=%s: the "
            "send raised after the hash was stored (%s); waiting on the hash",
            payout_id,
            tx_hash,
            type(exc).__name__,
        )

    return _await(self, payout_id, tx_hash)


def _hand_back(payout_id: uuid.UUID, tx_hash: str | None = None) -> bool:
    """Give the claim back (`processing -> pending`) and clear the hash, so a
    later call can try again. Only if the payout still holds this call's hash
    (or none), so it never undoes a release the sync recorded meanwhile.
    Returns True if it handed the claim back."""
    with session_scope() as session:
        handed = session.execute(
            update(StokvelPayout)
            .where(
                StokvelPayout.id == payout_id,
                StokvelPayout.release_status == RELEASE_PROCESSING,
                StokvelPayout.release_tx_hash.is_(None)
                if tx_hash is None
                else StokvelPayout.release_tx_hash == tx_hash,
            )
            .values(
                release_status=RELEASE_PENDING,
                release_tx_hash=None,
                updated_at=utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
    return handed.rowcount == 1


def _retry(task, payout_id: uuid.UUID, exc: Exception) -> str:
    """Retry the task, or give up once out of retries. Only called when
    nothing reached the chain, so the payout is `pending` and the scheduled
    release can try again later."""
    if task.request.retries >= task.max_retries:
        logger.error(
            "event=stokvel.release_unsent payout_id=%s retries=%s (%s): giving "
            "up; nothing was sent and the payout is pending",
            payout_id,
            task.request.retries,
            exc,
        )
        return "unsent"
    logger.warning(
        "event=stokvel.release_retry payout_id=%s retry=%s (%s): nothing was sent",
        payout_id,
        task.request.retries + 1,
        exc,
    )
    raise task.retry(countdown=RETRY_SECONDS, exc=exc) from None


def _resume(task, payout_id: uuid.UUID, status: str, tx_hash: str | None) -> str:
    """For a call that found the payout already claimed. Never sends:

    - `released`: nothing to do
    - `processing` with a hash: wait on that transaction
    - anything else: skip
    """
    if status == RELEASED:
        logger.info("payout %s is already released", payout_id)
        return "already_released"
    if status != RELEASE_PROCESSING:
        logger.info("payout %s is %s; not releasing", payout_id, status)
        return "skipped"
    if tx_hash is None:
        # Either another call is signing right now, or a worker crashed
        # before signing. Only a person can tell which.
        logger.warning(
            "event=stokvel.release_unsigned payout_id=%s: processing but no hash "
            "is stored; not sending",
            payout_id,
        )
        return "skipped"
    logger.info(
        "event=stokvel.release_resumed payout_id=%s tx_hash=%s: waiting on the "
        "stored transaction instead of sending another",
        payout_id,
        tx_hash,
    )
    return _await(task, payout_id, tx_hash)


def _await(task, payout_id: uuid.UUID, tx_hash: str) -> str:
    """Wait for the transaction to be mined, then record the release."""
    try:
        receipt = evm_service.wait_for_receipt(tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS)
    except evm_service.TransactionReverted:
        # Mined but failed, most likely because a `contribute` released the
        # round first (the sync records that). Give the claim back.
        _hand_back(payout_id, tx_hash)
        logger.warning(
            "event=stokvel.release_reverted payout_id=%s tx_hash=%s: claim handed "
            "back; a release by a contribute is recorded by the sync",
            payout_id,
            tx_hash,
        )
        return "reverted"
    except Exception as exc:
        # No receipt yet; it may still be mined. Retry on the same hash, and
        # after the last retry leave it `processing` for a person.
        if task.request.retries >= task.max_retries:
            logger.error(
                "event=stokvel.release_unconfirmed payout_id=%s tx_hash=%s "
                "retries=%s: no receipt, so the payout is left processing for a "
                "person; look the hash up on the explorer",
                payout_id,
                tx_hash,
                task.request.retries,
            )
            return "awaiting_receipt"
        logger.warning(
            "event=stokvel.release_receipt_retry payout_id=%s tx_hash=%s retry=%s (%s)",
            payout_id,
            tx_hash,
            task.request.retries + 1,
            type(exc).__name__,
        )
        raise task.retry(countdown=RETRY_SECONDS, exc=exc) from None

    return _record(payout_id, tx_hash, receipt)


def _record(payout_id: uuid.UUID, tx_hash: str, receipt) -> str:
    """Find this round's `RoundFinalised` event in the receipt and record it
    with `record_pool_release`. If that fails (e.g. a contribution in the
    pool is not recorded yet), the payout stays `processing` and the event
    sync records it later."""
    with session_scope() as session:
        payout = session.get(StokvelPayout, payout_id)
        cycle_id, round_ = payout.cycle_id, payout.round
    w3 = evm_service.get_web3()
    event = next(
        (
            event
            for event in stokvel_contract.round_finalised(receipt, w3)
            if event.args["round"] == round_
        ),
        None,
    )
    if event is None:
        logger.error(
            "event=stokvel.release_event_missing payout_id=%s tx_hash=%s: mined, "
            "but the receipt has no RoundFinalised for round %s; left processing "
            "for a person",
            payout_id,
            tx_hash,
            round_,
        )
        return "mined_unrecorded"
    try:
        with session_scope() as session:
            outcome = record_pool_release(
                session,
                cycle_id=cycle_id,
                round_=round_,
                member_id=evm_service.bytes32_to_uuid(event.args["memberId"]),
                pool=evm_service.from_base_units(event.args["pool"]),
                tx_hash=event.tx_hash,
                block_number=event.block_number,
            )
    except Exception as exc:
        logger.warning(
            "event=stokvel.release_left_for_sync payout_id=%s tx_hash=%s (%s: %s): "
            "mined, but not recorded here; the event sync records it",
            payout_id,
            tx_hash,
            type(exc).__name__,
            exc,
        )
        return "mined_unrecorded"
    logger.info(
        "event=stokvel.release_recorded payout_id=%s tx_hash=%s block=%s outcome=%s",
        payout_id,
        tx_hash,
        event.block_number,
        outcome,
    )
    return "released"


@celery.task(name="stokvel.release_due_rounds")
def release_due_rounds() -> int:
    """Runs on a timer and queues `release_pool` for each round that is due
    and that the contract agrees can be finalised.

    Does nothing while the contract is paused. Returns how many rounds were
    queued."""
    now = utcnow()
    with session_scope() as session:
        # Get rounds that are past their payout time, fully paid, and not
        # already being released.
        overdue = _overdue_rounds(session, now)
    if not overdue:
        return 0
    w3 = evm_service.get_web3()
    if stokvel_contract.paused(w3=w3):
        logger.info(
            "event=stokvel.release_sweep_paused rounds=%d: the contract is "
            "paused, so nothing is queued",
            len(overdue),
        )
        return 0
    queued = 0
    # Loop over the overdue rounds, checking with the contract if they are
    # finalisable, and enqueueing them for release.
    for cycle_id, stokvel_id, round_ in overdue:
        try:
            # Check with the contract if the round is finalisable.
            due = stokvel_contract.is_finalisable(stokvel_id, round_, w3=w3)
        except Exception as exc:
            logger.warning(
                "event=stokvel.release_sweep_check_failed cycle_id=%s round=%s "
                "(%s: %s): will retry next run",
                cycle_id,
                round_,
                type(exc).__name__,
                exc,
            )
            continue
        if not due:
            # Released on-chain but not yet recorded by the sync, or a
            # contribution the database has confirmed that the chain has not.
            continue
        try:
            # Try enqueue the release task for this round.
            queue_service.enqueue_release_pool(str(cycle_id), round_)
        except Exception:
            logger.exception(
                "event=stokvel.release_sweep_enqueue_failed cycle_id=%s round=%s: "
                "will retry next run",
                cycle_id,
                round_,
            )
            continue
        queued += 1
    if queued:
        logger.info("event=stokvel.release_sweep queued=%d", queued)
    return queued


def _overdue_rounds(session, now: datetime) -> list[tuple[uuid.UUID, uuid.UUID, int]]:
    """Return (cycle id, stokvel id, round) for each active cycle whose next
    unreleased round is past its payout time, fully paid, and not already
    being released.

    Also logs payouts stuck `processing` with no hash, since a worker may
    have crashed after claiming one."""
    # Whether the round already has a released payout
    released = (
        select(StokvelPayout.id)
        .where(
            StokvelPayout.cycle_id == StokvelRound.cycle_id,
            StokvelPayout.round == StokvelRound.round,
            StokvelPayout.release_status == RELEASED,
        )
        .exists()
    )
    # The next unreleased round of each cycle (rounds release in order)
    next_round = (
        select(StokvelRound.cycle_id, func.min(StokvelRound.round).label("round"))
        .where(~released)
        .group_by(StokvelRound.cycle_id)
        .subquery()
    )
    held_since = now - timedelta(seconds=Config().STOKVEL_RELEASE_STUCK_LOG_SECONDS)
    # Get the rows of active cycles and their next unreleased rounds.
    rows = session.execute(
        select(
            StokvelCycle.id,
            StokvelCycle.stokvel_id,
            StokvelCycle.total_rounds,
            StokvelRound.round,
            StokvelPayout.release_status,
            StokvelPayout.release_tx_hash,
            (StokvelPayout.updated_at <= held_since).label("stale"),
        )
        .select_from(StokvelCycle)
        .join(next_round, next_round.c.cycle_id == StokvelCycle.id)
        .join(
            StokvelRound,
            and_(
                StokvelRound.cycle_id == StokvelCycle.id,
                StokvelRound.round == next_round.c.round,
            ),
        )
        .outerjoin(
            StokvelPayout,
            and_(
                StokvelPayout.cycle_id == StokvelCycle.id,
                StokvelPayout.round == StokvelRound.round,
            ),
        )
        .where(
            StokvelCycle.status == StokvelCycleStatus.ACTIVE.value,
            StokvelCycle.registered_at.is_not(None),
            StokvelRound.payout_time <= now,
        )
        .order_by(StokvelRound.payout_time)
    ).all()

    overdue = []
    # loop through the rows of active cycles and their next unreleased rounds,
    # checking if they are overdue and fully paid, and logging any that are
    # stuck in processing with no hash.
    for cycle_id, stokvel_id, total_rounds, round_, status, tx_hash, stale in rows:
        if status == RELEASE_PROCESSING:
            if tx_hash is None and stale:
                logger.warning(
                    "event=stokvel.release_sweep_stuck cycle_id=%s round=%s: "
                    "overdue, and its payout has been processing with no hash "
                    "for too long; a release_pool may have stopped before "
                    "signing. Needs a person",
                    cycle_id,
                    round_,
                )
            continue
        if status not in (None, RELEASE_PENDING):
            continue
        if _fully_paid(session, cycle_id, round_, total_rounds):
            overdue.append((cycle_id, stokvel_id, round_))
    # Return a list of tuples containing the cycle id, stokvel id, and round
    # number for each overdue round that is fully paid and not already being
    # released.
    return overdue


def _fully_paid(session, cycle_id: uuid.UUID, round_: int, total_rounds: int) -> bool:
    """Checks in the database whether a round has met the contract's payment
    rule, before the sweep asks the contract over RPC."""
    rounds = [round_] if round_ + 1 == total_rounds else [round_, round_ + 1]
    paid = dict(
        session.execute(
            select(StokvelContribution.round, func.count())
            .where(
                StokvelContribution.cycle_id == cycle_id,
                StokvelContribution.round.in_(rounds),
                StokvelContribution.status == CONTRIBUTION_CONFIRMED,
            )
            .group_by(StokvelContribution.round)
        ).all()
    )
    return all(paid.get(r, 0) == total_rounds for r in rounds)
