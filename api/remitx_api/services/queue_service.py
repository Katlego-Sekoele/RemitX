"""Celery producer for the API.

The API owns a producer of its own rather than importing the worker's Celery
app. Two reasons:

1. It keeps the dependency one-directional. ``remitx_worker`` imports
   ``remitx_api`` for config and ORM models; if the API imported the worker
   back, the two form a cycle that only shows up at runtime.
2. Producing and consuming are genuinely different roles. The API never needs
   to know what a task does, only its name and which queue it goes on.
"""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor

import httpx
from celery import Celery

from remitx_api.config import Config

PROCESS_INTEGRATION_MESSAGE = "remitx_worker.tasks.process_integration_message"
SETTLE_REMITTANCE = "remitx_worker.tasks.settle_remittance"
BURN_TREASURY_TOKENS = "remitx_worker.tasks.burn_treasury_tokens"
CONFIRM_TREASURY_BURN = "remitx_worker.tasks.confirm_treasury_burn"
# The stokvel worker tasks (doc section 4), registered in
# `remitx_worker.stokvel_tasks` (R2-12, #234).
SUBMIT_CONTRIBUTION = "stokvel.submit_contribution"
CONFIRM_CONTRIBUTION = "stokvel.confirm_contribution"
START_CYCLE = "stokvel.start_cycle"
# Registered in `remitx_worker.stokvel_release` (R3-04, #241).
RELEASE_POOL = "stokvel.release_pool"
# Registered in `remitx_worker.stokvel_payouts` (R3-05, #242).
SETTLE_PAYOUT = "stokvel.settle_payout"
PAUSE_CONTRACT = "stokvel.pause_contract"
UNPAUSE_CONTRACT = "stokvel.unpause_contract"

# Admin pause waits on the worker result; long enough for one EVM send.
CONTRACT_PAUSE_TIMEOUT_SECONDS = 120

# Short on purpose, and not a deadline for the worker to finish booting. The
# ping exists to make Render's router start a spun-down instance, and that
# happens when the request arrives, not when it answers - a cold instance
# usually replies 502 long before it is ready. Nothing reads the response, so
# a longer wait would buy nothing and would only lengthen the join at
# interpreter exit.
WAKE_TIMEOUT_SECONDS = 5

logger = logging.getLogger(__name__)

producer = Celery("remitx_api", broker=Config.REDIS_URL, backend=Config.REDIS_URL)

# One thread, never more. A wake is a side effect of enqueueing rather than
# part of it, and the request that triggered it has already been answered.
# Threads are created on first submit, so an API with no WORKER_WAKE_URL
# never starts one.
_wake_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="worker-wake")
_wake_lock = threading.Lock()
_wake_in_flight = False


def _http_get(url: str, timeout: float) -> None:
    """GET the worker health URL without honoring process proxy env vars.

    ``urllib`` and ``httpx`` (with ``trust_env=True``) route through
    ``http_proxy`` / ``https_proxy``. A mis-set proxy on the API service
    makes browser visits to the worker work while server-side pings fail
    silently (logged only here).
    """
    with httpx.Client(trust_env=False, timeout=timeout) as client:
        # Do not raise on 502/503: Render's edge has already accepted the
        # request and started the spin-up; that is all the wake needs.
        client.get(url)


def _ping(url: str) -> None:
    global _wake_in_flight
    try:
        _http_get(url, WAKE_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        # Never the enqueue's problem: the task is already on Redis, and the
        # worker re-enqueues leftover PENDING rows when it does boot. A 502
        # here is the ordinary answer from an instance that is still starting.
        #
        # One line, no traceback: every frame of it is httpx internals, and
        # this fires on every cold start. The exception already names the
        # cause, and a wall of stack for the expected case buries the
        # unexpected one.
        logger.warning("worker wake at %s failed: %s", url, exc)
    finally:
        with _wake_lock:
            _wake_in_flight = False


def wake_worker() -> Future | None:
    """Ping the worker off the request path so a spun-down instance starts.

    Gated by ``WORKER_WAKE_URL``. Unset or blank is a no-op so local Compose
    and a future always-on worker stay producer-only.

    Wakes collapse: while one ping is outstanding, another is not sent. A
    worker booting because of an earlier ping drains the whole queue when it
    comes up, so a second ping for a message enqueued in the meantime would
    wake nothing that is not already waking. Without this, a burst of
    enqueues would queue a burst of pings behind a single thread and each
    would still be answered by the same booting instance.

    Returns the pending ping, or ``None`` when there is nothing to do.
    Callers are free to ignore it; tests use it to wait rather than sleep.
    """
    url = Config().WORKER_WAKE_URL
    if not url:
        return None
    global _wake_in_flight
    with _wake_lock:
        if _wake_in_flight:
            return None
        _wake_in_flight = True
    try:
        logger.info("worker wake ping scheduled for %s", url)
        return _wake_executor.submit(_ping, url)
    except Exception:
        with _wake_lock:
            _wake_in_flight = False
        raise


def enqueue_integration_message(message_id: str) -> None:
    """Put the task on Redis, then wake the worker - never the other way round.

    ``send_task`` is synchronous and raises if the broker cannot be reached
    (Celery retries the publish first), so returning from here means the
    message is on Redis and a caller that gets an exception knows it is not.
    The wake is deliberately outside that guarantee: it runs in the
    background and only logs on failure, because a task already on Redis is
    not lost by a ping that did not land.
    """
    producer.send_task(
        PROCESS_INTEGRATION_MESSAGE,
        args=[message_id],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def enqueue_settle_remittance(quote_id: str) -> None:
    """Settlement only ever needs `quote_id` (the group-update key everything
    else is guarded on).
    """
    producer.send_task(
        SETTLE_REMITTANCE,
        args=[quote_id],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def enqueue_burn_treasury_tokens(quote_id: str) -> None:
    """Enqueued by `settle_remittance` — burns the quote's UCTUSD on the
    XRPL EVM chain, waits for the receipt, and hands the result to
    `confirm_treasury_burn`.
    """
    producer.send_task(
        BURN_TREASURY_TOKENS,
        args=[quote_id],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def enqueue_confirm_treasury_burn(
    quote_id: str, tx_hash: str | None, error: str | None = None
) -> None:
    """Enqueued by `burn_treasury_tokens` once the burn has resolved: a
    confirmed receipt, or a failure (nothing sent, or a revert).

    `tx_hash` is `None` for a failed burn, in which case `error` carries the
    exception's message so `confirm_treasury_burn` can log it.
    """
    producer.send_task(
        CONFIRM_TREASURY_BURN,
        args=[quote_id, tx_hash, error],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def enqueue_submit_contribution(contribution_id: str) -> None:
    """Enqueued by `POST /stokvels/{id}/contributions` once the pending
    contribution and its legs are committed: the worker claims it and sends
    `contribute` from the Treasury Wallet (R2-12, #234). Only ever needs
    `contribution_id`, the key its claim is guarded on.
    """
    producer.send_task(
        SUBMIT_CONTRIBUTION,
        args=[contribution_id],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def enqueue_confirm_contribution(
    contribution_id: str,
    tx_hash: str | None,
    block_number: int | None = None,
    error: str | None = None,
) -> None:
    """Enqueued by `submit_contribution` once the `contribute` call has
    resolved: a mined receipt (`tx_hash` and its `block_number`), or a
    failure (`tx_hash` None, nothing sent or the call reverted, with `error`
    for the log).
    """
    producer.send_task(
        CONFIRM_CONTRIBUTION,
        args=[contribution_id, tx_hash, block_number, error],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def enqueue_start_cycle(cycle_id: str) -> None:
    """Enqueued by `POST /stokvels/{id}/cycles` once the cycle is committed
    `active`, and by the worker's `stokvel.register_started_cycles` sweep for
    one still unregistered: the worker registers it on the contract
    (`createStokvel` for a new stokvel, then `startCycle`; R2-10, #232). Only
    ever needs `cycle_id`: the task reads everything else from the database
    and the chain, so a redelivery repeats nothing.
    """
    producer.send_task(START_CYCLE, args=[cycle_id], queue=Config.CELERY_QUEUE)
    wake_worker()


def enqueue_release_pool(cycle_id: str, round_: int) -> None:
    """Ask the worker to send `finalise` for a round that became due with
    time rather than with a contribution: queued by the scheduled release
    (R3-11) and the Administrator's manual release (R3-10). Harmless to
    repeat: a released or claimed round is never sent twice."""
    producer.send_task(
        RELEASE_POOL,
        args=[cycle_id, round_],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def enqueue_settle_payout(payout_id: str) -> None:
    """Ask the worker to create a released payout's quote and remittance.
    Queued by the event sync for every released payout not yet started, so
    repeating it is harmless: only one delivery creates anything."""
    producer.send_task(
        SETTLE_PAYOUT,
        args=[payout_id],
        queue=Config.CELERY_QUEUE,
    )
    wake_worker()


def run_pause_contract() -> str:
    """Pause every stokvel on-chain; blocks until mined or the worker fails."""
    result = producer.send_task(PAUSE_CONTRACT, queue=Config.CELERY_QUEUE)
    wake_worker()
    return result.get(timeout=CONTRACT_PAUSE_TIMEOUT_SECONDS)


def run_unpause_contract() -> str:
    """Resume the vault; blocks until mined or the worker fails."""
    result = producer.send_task(UNPAUSE_CONTRACT, queue=Config.CELERY_QUEUE)
    wake_worker()
    return result.get(timeout=CONTRACT_PAUSE_TIMEOUT_SECONDS)
