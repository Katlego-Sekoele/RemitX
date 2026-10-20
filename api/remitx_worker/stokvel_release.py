"""Releasing a stokvel round's pool on-chain (R3-04, #241; doc section 4).

Most rounds release themselves: the `contribute` that makes a round due
releases it in the same transaction, and the event sync records it from the
`RoundFinalised` event. A round that becomes due with time instead (everyone
paid before its payout time, which is always the case for a cycle's last
round if it was paid early) needs someone to call the contract's `finalise`.
`stokvel.release_pool(cycle_id, round)` does that. It is queued by the
scheduled release (R3-11, #248) and the Administrator fallback (R3-10, #247),
never by the sync.

Either way the release is recorded through one guard,
`stokvel_ledger.record_pool_release` (OI-1, doc section 8), so it is booked once
whichever sees it first.

As with contributions (`stokvel_tasks.submit_contribution`):

- only the delivery whose guarded claim (`pending -> processing`) succeeds
  sends, and the hash is stored on the payout before the send, so a
  redelivery waits on that hash instead of sending a second `finalise`
- a call whose gas estimate reverts is never sent, and the claim is handed
  back (`processing -> pending`) so a later call can try again: no payout is
  failed from here
- once a hash may have reached the chain it is only ever waited on
"""

import logging
import uuid

from remitx_api.clock import utcnow
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from sqlalchemy import select, update

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

# The round is already released (a `contribute` got there first; the sync
# records it) or is not due yet (not fully paid, or its payout time has not
# passed; the scheduled release asks again later). Nothing to retry.
_NOTHING_TO_DO = frozenset({"AlreadyFinalised", "NotYetFinalisable"})

# The platform's to fix, as for contributions: the contract is paused, the
# Treasury lacks OPERATOR_ROLE, or the token transfer failed. Retried.
_RETRYABLE_REFUSALS = frozenset(
    {"EnforcedPause", "AccessControlUnauthorizedAccount", "SafeERC20FailedOperation"}
)


class _HashNotRecorded(Exception):
    """`release_pool` could not store a signed `finalise`'s hash, so it did
    not send it."""


@celery.task(bind=True, name="stokvel.release_pool", max_retries=MAX_RETRIES)
def release_pool(self, cycle_id: str, round_: int) -> str:
    """Send `finalise` for round `round_` of cycle `cycle_id`, then record the
    release from the receipt.

    The payout row is created if missing and claimed `pending ->
    processing`; a delivery that finds it already claimed waits on the
    stored hash, or does nothing if none was stored. A released round is
    left alone. Reports what happened, for the log and the tests.
    """
    try:
        target_id = uuid.UUID(cycle_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning("cycle id %r is not a valid id; skipping", cycle_id)
        return "skipped"

    with session_scope() as session:
        stokvel_id = session.scalar(
            select(StokvelCycle.stokvel_id).where(StokvelCycle.id == target_id)
        )
        if stokvel_id is None:
            logger.info("cycle %s does not exist; skipping", cycle_id)
            return "skipped"
        try:
            payout = ensure_payout(session, target_id, round_)
        except ReleaseConflict as exc:
            logger.error(
                "event=stokvel.release_unscheduled cycle_id=%s round=%s: %s",
                cycle_id,
                round_,
                exc,
            )
            return "skipped"
        claimed = session.execute(
            update(StokvelPayout)
            .where(
                StokvelPayout.id == payout.id,
                StokvelPayout.release_status == RELEASE_PENDING,
            )
            .values(release_status=RELEASE_PROCESSING, updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount == 0:
            session.refresh(payout)
            status, tx_hash = payout.release_status, payout.release_tx_hash
        payout_id = payout.id

    if claimed.rowcount == 0:
        return _resume(self, payout_id, status, tx_hash)

    recorded: list[str] = []

    def record(tx_hash: str) -> None:
        # Its own commit, before the send: a crash after this point leaves
        # the hash for a redelivery to wait on.
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

    try:
        w3 = evm_service.get_web3()
        tx_hash = stokvel_contract.finalise(stokvel_id, round_, on_signed=record, w3=w3)
    except _HashNotRecorded as exc:
        # The payout left `processing` or gained a hash between the claim and
        # now (the sync recorded it, say). Nothing was sent.
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
        # The RPC refused the signed `finalise`: it can never be mined, so its
        # stored hash goes with the claim.
        _hand_back(payout_id, recorded[0] if recorded else None)
        return _retry(self, payout_id, exc)
    except Exception as exc:
        if not recorded:
            # Failed before signing finished: nothing reached the chain.
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
    """`processing -> pending`, clearing the hash, so a later call can try
    again. Only if the payout still holds this delivery's hash (or none), so
    it never undoes a release the sync has recorded meanwhile."""
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
    """Nothing reached the chain and the claim is handed back: retry, or give
    up once the retries are spent. The payout stays `pending`, so the
    scheduled release can ask again."""
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
    """A delivery that found nothing pending to claim: never sends."""
    if status == RELEASED:
        logger.info("payout %s is already released", payout_id)
        return "already_released"
    if status != RELEASE_PROCESSING:
        logger.info("payout %s is %s; not releasing", payout_id, status)
        return "skipped"
    if tx_hash is None:
        # Another delivery is signing right now, or a worker stopped after
        # the claim and before signing (nothing was sent). Telling those
        # apart needs a person.
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
    """Wait for the receipt, then record the release from its event."""
    try:
        receipt = evm_service.wait_for_receipt(tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS)
    except evm_service.TransactionReverted:
        # Mined and failed, most likely because a `contribute` released the
        # round first. The sync records that release; this one only hands the
        # claim back if the payout still holds its hash.
        _hand_back(payout_id, tx_hash)
        logger.warning(
            "event=stokvel.release_reverted payout_id=%s tx_hash=%s: claim handed "
            "back; a release by a contribute is recorded by the sync",
            payout_id,
            tx_hash,
        )
        return "reverted"
    except Exception as exc:
        # No answer: the transaction may still be mined. Wait on the same
        # hash again; after the retries, leave it processing for a person.
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
    """Record the mined release through `record_pool_release`. If that fails (a
    contribution in the pool is not recorded yet, so the `STOKVEL` balance
    would go below zero), the payout stays `processing` with its hash and the
    event sync records it from the `RoundFinalised` event."""
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
