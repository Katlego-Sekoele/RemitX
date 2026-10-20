"""Stokvel worker tasks (doc section 4).

R2-12 (#234): `stokvel.submit_contribution` takes a `pending` contribution
from `POST /stokvels/{id}/contributions` (R2-11) and sends `contribute` from
the Treasury Wallet; `stokvel.confirm_contribution` records the outcome. As
in settlement (`tasks.burn_treasury_tokens` / `confirm_treasury_burn`), the
task that talks to the chain is separate from the one that writes the
result, so the database step can be retried on its own.

A contribution is never `confirmed` before its transaction is mined, and
nothing moves a balance before then: until `confirm_contribution`, its fiat,
token and fee legs are only `pending`/`processing`, which hold the member's
available balance. A reverted or refused `contribute` fails the contribution
and its legs, which releases that hold; no balance needs reversing.

Duplicate messages: only the delivery whose guarded claim
(`pending -> processing`) succeeds may send. Its hash is stored before the
send, so a redelivery waits on that hash rather than paying twice.

R2-13 (#235): `stokvel.sync_events` reads the contract's events into the
database on the beat (`stokvel_sync` applies them).

R2-10 (#232) adds the cycle tasks to this module.
"""

import logging
import uuid

from hexbytes import HexBytes
from remitx_api.clock import utcnow
from remitx_api.config import Config
from remitx_api.models.orm.stokvel_contribution import (
    StokvelContribution,
    StokvelContributionStatus,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_held_event import (
    HELD_FAILED,
    HELD_WAITING,
    StokvelHeldEvent,
)
from remitx_api.models.orm.stokvel_sync_state import StokvelSyncState
from remitx_api.models.orm.transaction import (
    STATUS_FAILED as TX_STATUS_FAILED,
    STATUS_PENDING as TX_STATUS_PENDING,
    STATUS_PROCESSING as TX_STATUS_PROCESSING,
    Transaction,
)
from remitx_api.services import queue_service
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from web3 import Web3

from remitx_worker import evm_service, stokvel_contract, stokvel_payouts, stokvel_sync
from remitx_worker.celery_app import celery
from remitx_worker.db import session_scope
from remitx_worker.stokvel_ledger import (
    IN_FLIGHT as _IN_FLIGHT,
    LEGS_IN_FLIGHT as _LEGS_IN_FLIGHT,
    contribution_legs as _legs,
    record_mined,
)

logger = logging.getLogger(__name__)

PENDING = StokvelContributionStatus.PENDING.value
PROCESSING = StokvelContributionStatus.PROCESSING.value
CONFIRMED = StokvelContributionStatus.CONFIRMED.value
FAILED = StokvelContributionStatus.FAILED.value

# How long one delivery waits for a receipt, and how often and how many times
# the task retries (a wait with no answer, or a send that could not be made)
# before leaving the contribution for a person or failing it.
RECEIPT_TIMEOUT_SECONDS = 120
RETRY_SECONDS = 60
MAX_RETRIES = 10

# Refusals that are the platform's to fix, not the member's: the contract is
# paused (OI-4); the Treasury is short of UCTUSD or of allowance (section 6:
# operations faults); the Treasury lacks OPERATOR_ROLE (a deployment fault);
# or the token transfer itself failed. Retried, so a contribution survives the
# fix; failed only once the retries run out. Every other refusal is a rule the
# contract enforces (NotMember, AlreadyPaid, WrongRound, CycleNotOpen, ...):
# it fails the contribution at once.
_RETRYABLE_REFUSALS = frozenset(
    {
        "EnforcedPause",
        "ERC20InsufficientBalance",
        "ERC20InsufficientAllowance",
        "AccessControlUnauthorizedAccount",
        "SafeERC20FailedOperation",
    }
)


class _HashNotRecorded(Exception):
    """`submit_contribution` could not store a signed `contribute`'s hash, so
    it did not send it."""


def _parse(contribution_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(contribution_id)
    except (AttributeError, TypeError, ValueError):
        logger.warning(
            "contribution id %r is not a valid id; skipping", contribution_id
        )
        return None


@celery.task(bind=True, name="stokvel.submit_contribution", max_retries=MAX_RETRIES)
def submit_contribution(self, contribution_id: str) -> str:
    """Claim a pending contribution and send `contribute` for it.

    The guarded claim (`pending -> processing`, with its legs) means only one
    delivery ever sends. The hash is stored on the contribution after signing
    and before the send; a redelivery that finds the contribution already
    claimed waits on that hash, or does nothing if none was stored.

    Before sending, the Treasury's allowance for the vault is checked and
    topped up if short (section 1). A call the gas estimate shows would
    revert is never sent: a rule refusal fails the contribution; a platform
    one (paused, Treasury short) is retried. When nothing was signed, or the
    RPC refused the send, the claim is handed back (`processing -> pending`)
    and the task retries; it fails the contribution only once `MAX_RETRIES`
    is spent. Once a hash may have reached the chain it is only ever waited
    on, never failed or resent from here.
    """
    target_id = _parse(contribution_id)
    if target_id is None:
        return "skipped"

    with session_scope() as session:
        claimed = session.execute(
            update(StokvelContribution)
            .where(
                StokvelContribution.id == target_id,
                StokvelContribution.status == PENDING,
            )
            .values(status=PROCESSING)
            .execution_options(synchronize_session=False)
        )
        contribution = session.get(StokvelContribution, target_id)
        if contribution is None:
            logger.info("contribution %s does not exist; skipping", contribution_id)
            return "skipped"
        if claimed.rowcount == 0:
            status, tx_hash = contribution.status, contribution.evm_tx_hash
        else:
            session.execute(
                update(Transaction)
                .where(
                    Transaction.tx_id.in_(_legs(contribution)),
                    Transaction.status == TX_STATUS_PENDING,
                )
                .values(status=TX_STATUS_PROCESSING, processed_at=utcnow())
                .execution_options(synchronize_session=False)
            )
            stokvel_id = session.scalar(
                select(StokvelCycle.stokvel_id).where(
                    StokvelCycle.id == contribution.cycle_id
                )
            )
            round_, member_id = contribution.round, contribution.member_id
            amount_token = contribution.amount_token

    if claimed.rowcount == 0:
        return _resume(self, contribution_id, status, tx_hash)

    recorded: list[str] = []

    def record(tx_hash: str) -> None:
        # Its own commit, before the send: a crash after this point leaves
        # the hash for a redelivery to wait on.
        with session_scope() as session:
            stored = session.execute(
                update(StokvelContribution)
                .where(
                    StokvelContribution.id == target_id,
                    StokvelContribution.status == PROCESSING,
                    StokvelContribution.evm_tx_hash.is_(None),
                )
                .values(evm_tx_hash=tx_hash)
                .execution_options(synchronize_session=False)
            )
        if stored.rowcount != 1:
            raise _HashNotRecorded(tx_hash)
        recorded.append(tx_hash)

    try:
        w3 = evm_service.get_web3()
        stokvel_contract.ensure_allowance(amount_token, w3=w3)
        tx_hash = stokvel_contract.contribute(
            stokvel_id, round_, member_id, on_signed=record, w3=w3
        )
    except _HashNotRecorded as exc:
        # The contribution left `processing` or gained a hash between the
        # claim and now. Nothing was sent, and it is not this delivery's.
        logger.error(
            "event=stokvel.contribution_not_recorded contribution_id=%s "
            "tx_hash=%s: no longer processing without a hash, so the signed "
            "contribute was not sent",
            contribution_id,
            exc,
        )
        return "skipped"
    except stokvel_contract.ContractRefused as exc:
        if exc.error in _RETRYABLE_REFUSALS:
            return _retry_unsent(self, target_id, contribution_id, exc)
        logger.error(
            "event=stokvel.contribution_refused contribution_id=%s error=%s: the "
            "contract would revert, so nothing was sent",
            contribution_id,
            exc.error or exc,
        )
        queue_service.enqueue_confirm_contribution(
            contribution_id, None, None, str(exc)
        )
        return "failed"
    except evm_service.TransactionRejected as exc:
        # The RPC refused a signed transaction: it is in no mempool and can
        # never be mined. If it was the `contribute`, its stored hash is
        # dropped with the claim. It may instead have been the allowance's
        # `approve`, whose hash was never stored on the contribution, so only
        # a hash `record` stored counts as ours.
        rejected = recorded[0] if recorded else None
        return _retry_unsent(self, target_id, contribution_id, exc, rejected)
    except Exception as exc:
        if not recorded:
            # Failed before signing finished: nothing reached the chain.
            return _retry_unsent(self, target_id, contribution_id, exc)
        # The hash is stored, so the send may have reached the chain even
        # though it raised. Wait on it; never fail it from here.
        (tx_hash,) = recorded
        logger.warning(
            "event=stokvel.contribution_send_uncertain contribution_id=%s "
            "tx_hash=%s: the send raised after the hash was stored (%s); "
            "waiting on the hash",
            contribution_id,
            tx_hash,
            type(exc).__name__,
        )

    return _await(self, contribution_id, tx_hash)


def _retry_unsent(
    task,
    target_id: uuid.UUID,
    contribution_id: str,
    exc: Exception,
    rejected_hash: str | None = None,
) -> str:
    """Nothing reached the chain: hand the claim back and retry, or fail the
    contribution once the retries are spent.

    `rejected_hash` is the hash of a transaction the RPC refused. It never
    existed, so it is cleared either way: left on a failed row, it would
    block the member's retry, whose identical transaction (same calldata,
    and the same nonce, since nothing was mined) signs to the same hash and
    hits the unique index on `evm_tx_hash`. A reverted transaction's hash is
    kept; it never comes through here."""
    if task.request.retries >= task.max_retries:
        if rejected_hash is not None:
            with session_scope() as session:
                session.execute(
                    update(StokvelContribution)
                    .where(
                        StokvelContribution.id == target_id,
                        StokvelContribution.status == PROCESSING,
                        StokvelContribution.evm_tx_hash == rejected_hash,
                    )
                    .values(evm_tx_hash=None)
                    .execution_options(synchronize_session=False)
                )
        logger.error(
            "event=stokvel.contribution_unsent contribution_id=%s retries=%s "
            "(%s): giving up; nothing was sent",
            contribution_id,
            task.request.retries,
            exc,
        )
        queue_service.enqueue_confirm_contribution(
            contribution_id, None, None, str(exc)
        )
        return "failed"
    with session_scope() as session:
        released = session.execute(
            update(StokvelContribution)
            .where(
                StokvelContribution.id == target_id,
                StokvelContribution.status == PROCESSING,
                StokvelContribution.evm_tx_hash.is_(None)
                if rejected_hash is None
                else StokvelContribution.evm_tx_hash == rejected_hash,
            )
            .values(status=PENDING, evm_tx_hash=None)
            .execution_options(synchronize_session=False)
        )
        if released.rowcount == 1:
            contribution = session.get(StokvelContribution, target_id)
            session.execute(
                update(Transaction)
                .where(
                    Transaction.tx_id.in_(_legs(contribution)),
                    Transaction.status == TX_STATUS_PROCESSING,
                )
                .values(status=TX_STATUS_PENDING, processed_at=None)
                .execution_options(synchronize_session=False)
            )
    if released.rowcount != 1:
        logger.warning(
            "contribution %s changed while its send was being retried; not retrying",
            contribution_id,
        )
        return "skipped"
    logger.warning(
        "event=stokvel.contribution_retry contribution_id=%s retry=%s (%s): "
        "nothing was sent; claim handed back",
        contribution_id,
        task.request.retries + 1,
        exc,
    )
    raise task.retry(countdown=RETRY_SECONDS, exc=exc) from None


def _resume(task, contribution_id: str, status: str, tx_hash: str | None) -> str:
    """A delivery that found nothing pending to claim: never sends."""
    if status != PROCESSING:
        logger.info(
            "contribution %s is %s; already handled",
            contribution_id,
            status,
        )
        return "skipped"
    if tx_hash is None:
        # Another delivery is signing right now, or a worker stopped after
        # the claim and before signing (nothing was sent). Telling those
        # apart needs a person.
        logger.warning(
            "event=stokvel.contribution_unsigned contribution_id=%s: processing "
            "but no hash is stored; not sending",
            contribution_id,
        )
        return "skipped"
    logger.info(
        "event=stokvel.contribution_resumed contribution_id=%s tx_hash=%s: "
        "waiting on the stored transaction instead of sending another",
        contribution_id,
        tx_hash,
    )
    return _await(task, contribution_id, tx_hash)


def _await(task, contribution_id: str, tx_hash: str) -> str:
    """Wait for the receipt, then hand the outcome to `confirm_contribution`."""
    try:
        receipt = evm_service.wait_for_receipt(tx_hash, timeout=RECEIPT_TIMEOUT_SECONDS)
    except evm_service.TransactionReverted as exc:
        # Mined and failed: no tokens moved, so the contribution can fail.
        logger.error(
            "event=stokvel.contribution_reverted contribution_id=%s tx_hash=%s",
            contribution_id,
            tx_hash,
        )
        queue_service.enqueue_confirm_contribution(
            contribution_id, None, None, str(exc)
        )
        return "failed"
    except Exception as exc:
        # No answer: the transaction may still be mined. Wait on the same
        # hash again; after the retries, leave it processing for a person.
        if task.request.retries >= task.max_retries:
            logger.error(
                "event=stokvel.contribution_unconfirmed contribution_id=%s "
                "tx_hash=%s retries=%s: no receipt, so the contribution is left "
                "processing for a person; look the hash up on the explorer",
                contribution_id,
                tx_hash,
                task.request.retries,
            )
            return "awaiting_receipt"
        logger.warning(
            "event=stokvel.contribution_receipt_retry contribution_id=%s "
            "tx_hash=%s retry=%s (%s)",
            contribution_id,
            tx_hash,
            task.request.retries + 1,
            type(exc).__name__,
        )
        raise task.retry(countdown=RETRY_SECONDS, exc=exc) from None

    queue_service.enqueue_confirm_contribution(
        contribution_id, tx_hash, receipt["blockNumber"]
    )
    return "mined"


@celery.task(name="stokvel.confirm_contribution")
def confirm_contribution(
    contribution_id: str,
    tx_hash: str | None,
    block_number: int | None = None,
    error: str | None = None,
) -> str:
    """Record the outcome of `submit_contribution`. Database only.

    `tx_hash` (with its `block_number`) is given only once the receipt has
    confirmed the `contribute`: then `record_mined` confirms it and moves its
    balances, in one commit.

    `tx_hash` None means nothing was sent or the call reverted: the
    contribution and its legs become `failed`, which frees the member's held
    balance and reopens their place in the round. No balance changes.

    Guarded on the contribution still being `pending` or `processing`, so a
    replayed message changes nothing and never credits twice. The event sync
    (R2-13, #235) records a mined contribution through the same guard.
    """
    target_id = _parse(contribution_id)
    if target_id is None:
        return "skipped"

    if tx_hash is not None:
        if block_number is None:
            raise ValueError("a confirmed contribution needs its block number")
        with session_scope() as session:
            settled = record_mined(session, target_id, tx_hash, block_number)
        if settled is None:
            logger.info(
                "contribution %s is not pending or processing; already "
                "recorded or unknown",
                contribution_id,
            )
            return "skipped"
        logger.info(
            "contribution %s confirmed (%s, block %s): %d legs confirmed and settled",
            contribution_id,
            tx_hash,
            block_number,
            settled,
        )
        return "confirmed"

    with session_scope() as session:
        changed = session.execute(
            update(StokvelContribution)
            .where(
                StokvelContribution.id == target_id,
                StokvelContribution.status.in_(_IN_FLIGHT),
            )
            .values(status=FAILED)
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount == 0:
            logger.info(
                "contribution %s is not pending or processing; already "
                "recorded or unknown",
                contribution_id,
            )
            return "skipped"
        session.execute(
            update(Transaction)
            .where(
                Transaction.tx_id.in_(
                    _legs(session.get(StokvelContribution, target_id))
                ),
                Transaction.status.in_(_LEGS_IN_FLIGHT),
            )
            .values(status=TX_STATUS_FAILED)
            .execution_options(synchronize_session=False)
        )
    logger.error(
        "contribution %s failed (%s): it and its legs are marked failed; "
        "no balance changed",
        contribution_id,
        error or "unknown error",
    )
    return "failed"


class _CursorRaced(Exception):
    """Another `sync_events` run moved or created the cursor between this
    run's read and its write. Raised only from the cursor write, and the
    range's transaction rolls back."""


# Held events retried per run, oldest first.
_HELD_RETRY_LIMIT = 200


@celery.task(name="stokvel.sync_events")
def sync_events() -> str:
    """Read the stokvel contract's events since the cursor and apply them
    (R2-13, #235). Run by the worker's beat every
    `STOKVEL_SYNC_INTERVAL_SECONDS`.

    First retries the held events (`StokvelHeldEvent`), so a release task or
    a fix that has since arrived catches them up. Then reads up to
    `STOKVEL_SYNC_MAX_RANGES` ranges of `STOKVEL_SYNC_BLOCK_RANGE` blocks,
    staying `STOKVEL_SYNC_CONFIRMATIONS` blocks behind the head. Each range is
    one transaction: a compare-and-set on the cursor (only from the block
    this run read; on Postgres an overlapping run waits, then matches nothing
    and stops), then the range's events in chain order.

    Each event is applied in its own savepoint. One that waits for something
    that does not exist yet, fails, will not decode, or disagrees with the
    database is held instead, so the cursor moves on and no single event can
    stop the sync, and nothing is lost. An RPC error leaves the cursor for the
    next run. Every handler is guarded, so a replayed range changes nothing.
    """
    config = Config()
    address = config.STOKVEL_CONTRACT_ADDRESS
    if not address:
        logger.info("STOKVEL_CONTRACT_ADDRESS is not set; no events to sync")
        return "skipped"
    key = address.lower()

    with session_scope() as session:
        state = session.get(StokvelSyncState, key)
        last = None if state is None else state.last_processed_block
    has_cursor = last is not None
    if not has_cursor:
        if config.STOKVEL_SYNC_START_BLOCK is None:
            # Without it the first run would scan from genesis: thousands of
            # eth_getLogs calls before the deployment block.
            logger.error(
                "event=stokvel.sync_misconfigured: STOKVEL_CONTRACT_ADDRESS is "
                "set but STOKVEL_SYNC_START_BLOCK is not; set it to the "
                "contract's deployment block"
            )
            return "misconfigured"
        last = config.STOKVEL_SYNC_START_BLOCK - 1

    try:
        w3 = evm_service.get_web3()
        head = w3.eth.block_number - config.STOKVEL_SYNC_CONFIRMATIONS
    except Exception as exc:
        logger.warning("event=stokvel.sync_rpc_error (%s): will retry next run", exc)
        return "rpc_error"

    outcomes: dict[str, int] = {}
    _retry_held(key, w3, outcomes)

    for _ in range(config.STOKVEL_SYNC_MAX_RANGES):
        from_block = last + 1
        if from_block > head:
            break
        to_block = min(head, from_block + config.STOKVEL_SYNC_BLOCK_RANGE - 1)

        try:
            logs = stokvel_contract.fetch_logs(from_block, to_block, w3)
        except Exception as exc:
            logger.warning(
                "event=stokvel.sync_rpc_error from_block=%s to_block=%s (%s): "
                "will retry next run",
                from_block,
                to_block,
                exc,
            )
            break

        try:
            with session_scope() as session:
                _move_cursor(session, key, has_cursor, last, to_block)
                for log in logs:
                    _apply_log(session, key, w3, log, outcomes)
        except _CursorRaced:
            with session_scope() as session:
                state = session.get(StokvelSyncState, key)
                last = None if state is None else state.last_processed_block
            logger.info(
                "event=stokvel.sync_raced: another run moved the cursor to %s; "
                "stopping",
                last,
            )
            break
        last, has_cursor = to_block, True

    # Every release recorded so far, by this run or `release_pool`, is paid
    # out (R3-05). After the commits above, so only recorded releases go.
    try:
        queued = stokvel_payouts.queue_released_payouts()
        if queued:
            outcomes["payouts_queued"] = queued
    except Exception as exc:
        logger.warning(
            "event=stokvel.payout_queue_failed (%s): queued on the next run", exc
        )

    summary = ", ".join(f"{count} {name}" for name, count in sorted(outcomes.items()))
    logger.info(
        "event=stokvel.sync_done cursor=%s head=%s %s",
        last,
        head,
        summary or "no events",
    )
    return f"synced to {last}"


def _move_cursor(session, key: str, has_cursor: bool, last: int, to_block: int):
    """Compare-and-set the cursor from `last` to `to_block`, or create it.
    Raises `_CursorRaced` if another run got there first."""
    if has_cursor:
        moved = session.execute(
            update(StokvelSyncState)
            .where(
                StokvelSyncState.id == key,
                StokvelSyncState.last_processed_block == last,
            )
            .values(last_processed_block=to_block, updated_at=utcnow())
            .execution_options(synchronize_session=False)
        )
        if moved.rowcount != 1:
            raise _CursorRaced()
        return
    session.add(StokvelSyncState(id=key, last_processed_block=to_block))
    try:
        session.flush()
    except IntegrityError as exc:
        # Only the cursor's own insert can mean another run created it
        # first; event errors never reach here (each has its savepoint).
        raise _CursorRaced() from exc


def _count(outcomes: dict[str, int], outcome: str) -> None:
    outcomes[outcome] = outcomes.get(outcome, 0) + 1


def _apply_log(session, key: str, w3, log, outcomes: dict[str, int]) -> None:
    """Decode and apply one log from a range, holding it if it cannot be."""
    try:
        event = stokvel_contract.decode_log(log, w3)
    except Exception as exc:
        _hold_undecoded(session, key, log, exc)
        _count(outcomes, "held_failed")
        return
    held_reason, error, outcome = _try_apply(session, event)
    if held_reason is None:
        _count(outcomes, outcome)
        return
    _hold(session, key, event, held_reason, error)
    _count(outcomes, f"held_{held_reason}")


def _try_apply(session, event) -> tuple[str | None, str | None, str]:
    """Apply `event` in a savepoint. Returns (held reason or None, error,
    outcome). On a failure the savepoint rolls back, so nothing it did
    stays."""
    savepoint = session.begin_nested()
    try:
        outcome = stokvel_sync.apply_event(session, event)
    except stokvel_sync.EventNeedsAPerson as exc:
        savepoint.rollback()
        return HELD_FAILED, str(exc), "failed"
    except Exception as exc:
        savepoint.rollback()
        return HELD_FAILED, f"{type(exc).__name__}: {exc}", "failed"
    savepoint.commit()
    if outcome == stokvel_sync.WAITING:
        return HELD_WAITING, None, outcome
    return None, None, outcome


def _held_row(session, key: str, tx_hash: str, log_index: int):
    return session.scalar(
        select(StokvelHeldEvent).where(
            StokvelHeldEvent.contract_address == key,
            StokvelHeldEvent.tx_hash == tx_hash,
            StokvelHeldEvent.log_index == log_index,
        )
    )


def _hold(session, key: str, event, reason: str, error: str | None) -> None:
    row = _held_row(session, key, event.tx_hash, event.log_index)
    if row is not None:  # a replayed range: already held
        return
    session.add(
        StokvelHeldEvent(
            contract_address=key,
            tx_hash=event.tx_hash,
            log_index=event.log_index,
            block_number=event.block_number,
            name=event.name,
            args=stokvel_sync.args_to_json(event.args),
            reason=reason,
            error=error,
        )
    )
    log = logger.error if reason == HELD_FAILED else logger.info
    log(
        "event=stokvel.sync_event_held reason=%s name=%s tx_hash=%s log_index=%s "
        "block=%s%s",
        reason,
        event.name,
        event.tx_hash,
        event.log_index,
        event.block_number,
        f": {error}" if error else "",
    )


def _raw_log_to_json(log) -> dict:
    def hexed(value):
        return (
            "0x" + bytes(value).hex() if isinstance(value, bytes | bytearray) else value
        )

    return {
        key: [hexed(topic) for topic in value] if key == "topics" else hexed(value)
        for key, value in dict(log).items()
    }


def _raw_log_from_json(raw: dict) -> dict:
    hex_fields = {"data", "transactionHash", "blockHash"}
    return {
        key: [HexBytes(topic) for topic in value]
        if key == "topics"
        else HexBytes(value)
        if key in hex_fields
        else value
        for key, value in raw.items()
    }


def _hold_undecoded(session, key: str, log, exc: Exception) -> None:
    tx_hash = Web3.to_hex(log["transactionHash"])
    if _held_row(session, key, tx_hash, log["logIndex"]) is not None:
        return
    error = f"did not decode: {type(exc).__name__}: {exc}"
    session.add(
        StokvelHeldEvent(
            contract_address=key,
            tx_hash=tx_hash,
            log_index=log["logIndex"],
            block_number=log["blockNumber"],
            raw_log=_raw_log_to_json(log),
            reason=HELD_FAILED,
            error=error,
        )
    )
    logger.error(
        "event=stokvel.sync_event_held reason=failed tx_hash=%s log_index=%s "
        "block=%s: %s",
        tx_hash,
        log["logIndex"],
        log["blockNumber"],
        error,
    )


def _retry_held(key: str, w3, outcomes: dict[str, int]) -> None:
    """Try the unresolved held events again, oldest first, each in its own
    savepoint. One that now applies is resolved; one that still cannot keeps
    its row with the latest reason and error."""
    with session_scope() as session:
        held = session.scalars(
            select(StokvelHeldEvent)
            .where(
                StokvelHeldEvent.contract_address == key,
                StokvelHeldEvent.resolved_at.is_(None),
            )
            .order_by(StokvelHeldEvent.block_number, StokvelHeldEvent.log_index)
            .limit(_HELD_RETRY_LIMIT)
        ).all()
        for row in held:
            try:
                event = (
                    stokvel_contract.decode_log(_raw_log_from_json(row.raw_log), w3)
                    if row.raw_log is not None
                    else stokvel_contract.ContractEvent(
                        name=row.name,
                        args=stokvel_sync.args_from_json(row.args),
                        tx_hash=row.tx_hash,
                        block_number=row.block_number,
                        log_index=row.log_index,
                    )
                )
            except Exception as exc:
                row.attempts += 1
                row.error = f"did not decode: {type(exc).__name__}: {exc}"
                continue
            reason, error, outcome = _try_apply(session, event)
            if reason is None:
                row.resolved_at = utcnow()
                _count(outcomes, "resolved")
                logger.info(
                    "event=stokvel.sync_event_resolved name=%s tx_hash=%s "
                    "log_index=%s outcome=%s attempts=%s",
                    event.name,
                    event.tx_hash,
                    event.log_index,
                    outcome,
                    row.attempts,
                )
                continue
            row.attempts += 1
            row.reason, row.error = reason, error
            _count(outcomes, f"still_{reason}")
