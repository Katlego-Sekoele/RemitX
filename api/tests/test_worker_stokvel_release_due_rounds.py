"""The scheduled release (R3-11, #248): `stokvel.release_due_rounds`, which
queues `stokvel.release_pool` for every round that has become due with time.

Same conventions as test_worker_stokvel_release.py, whose fixtures this
reuses: a two-member, two-round cycle on a scratch SQLite file. The chain is
`FakeVault`, which applies the contract's release rule (`_isFinalisable`)
against a clock the test moves; the task reads the same clock. The enqueue is
captured, and each test runs the queued `release_pool` itself, as a worker
would.

The ticket's three cases: everyone pays early and the round releases only
after its payout time; a member pays after the payout time and the round
releases; a double trigger releases once.
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from remitx_api.config import Config
from remitx_api.models.orm.stokvel_contribution import (
    STATUS_CONFIRMED,
    StokvelContribution,
)
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_worker import evm_service, stokvel_contract, stokvel_release
from remitx_worker.celery_app import celery
from remitx_worker.stokvel_ledger import ensure_payout
from remitx_worker.stokvel_release import release_due_rounds, release_pool
from sqlalchemy import select
from tests.test_worker_stokvel_contribution import (
    BLOCK,
    CONTRIBUTION,
    FIAT,
    W3,
    pending,
    session_factory,
)
from tests.test_worker_stokvel_release import (
    POOL,
    _balances,
    _event,
    _fund,
    _payouts,
    _record,
    _release_legs,
    cycle,
)

PAYOUT_TIMES = [
    datetime(2026, 11, 2, 9, 0, tzinfo=UTC),
    datetime(2026, 11, 9, 9, 0, tzinfo=UTC),
]
CONTRIBUTE_HASH = "0x" + "c1" * 32


def _finalise_hash(round_: int) -> str:
    return "0x" + f"e{round_}" * 32


class FakeVault:
    """The StokvelVault's release, without a chain: `isFinalisable`, `paused`,
    `finalise` and its receipt, and `contribute`, which releases every round
    that is now due (`_releaseDue`). `now` is the block time."""

    def __init__(self, cycle):
        self.cycle = cycle
        self.now = PAYOUT_TIMES[0] - timedelta(hours=1)
        self.paid = [0, 0]
        self.next_to_finalise = 0
        self.is_paused = False
        self.asked = []
        self.sent = []
        self.released = {}  # round -> the hash that released it
        self.read_error = None

    def _due(self, round_: int) -> bool:
        n = len(self.paid)
        return (
            round_ == self.next_to_finalise
            and round_ < n
            and self.paid[round_] == n
            and (round_ + 1 == n or self.paid[round_ + 1] == n)
            and self.now >= PAYOUT_TIMES[round_]
        )

    def _release(self, round_: int, tx_hash: str) -> None:
        self.released[round_] = tx_hash
        self.next_to_finalise = round_ + 1

    def paused(self, w3=None):
        assert w3 is W3
        return self.is_paused

    def is_finalisable(self, stokvel_id, round_, w3=None):
        assert (stokvel_id, w3) == (self.cycle["stokvel_id"], W3)
        self.asked.append(round_)
        if self.read_error is not None:
            raise self.read_error
        return self._due(round_)

    def contribute(self, round_: int) -> list[int]:
        """A member's payment; the rounds it released."""
        self.paid[round_] += 1
        released = []
        while self._due(self.next_to_finalise):
            released.append(self.next_to_finalise)
            self._release(self.next_to_finalise, CONTRIBUTE_HASH)
        return released

    def finalise(self, stokvel_id, round_, *, on_signed=None, w3=None):
        assert (stokvel_id, w3) == (self.cycle["stokvel_id"], W3)
        if round_ < self.next_to_finalise:
            raise stokvel_contract.ContractRefused("AlreadyFinalised", "reverted")
        if not self._due(round_):
            raise stokvel_contract.ContractRefused("NotYetFinalisable", "reverted")
        tx_hash = _finalise_hash(round_)
        if on_signed is not None:
            on_signed(tx_hash)
        self._release(round_, tx_hash)
        self.sent.append(round_)
        return tx_hash

    def wait_for_receipt(self, tx_hash, timeout=120, w3=None):
        return {"transactionHash": tx_hash, "status": 1, "blockNumber": BLOCK}

    def round_finalised(self, receipt, w3):
        return [
            _event(self.cycle, round_, tx_hash=tx_hash)
            for round_, tx_hash in self.released.items()
            if tx_hash == receipt["transactionHash"]
        ]


@pytest.fixture
def vault(monkeypatch, session_factory, cycle):
    """The cycle registered on-chain with `PAYOUT_TIMES`, and the faked vault.
    The task's clock is the vault's block time."""
    with session_factory() as session:
        session.get(StokvelCycle, cycle["id"]).registered_at = datetime.now(UTC)
        for round_, payout_time in enumerate(PAYOUT_TIMES):
            row = session.get(StokvelRound, (cycle["id"], round_))
            row.start_time = payout_time - timedelta(days=7)
            row.deadline = payout_time - timedelta(days=1)
            row.payout_time = payout_time
        session.commit()
    fake = FakeVault(cycle)
    monkeypatch.setattr(stokvel_release, "utcnow", lambda: fake.now)
    monkeypatch.setattr(stokvel_contract, "paused", fake.paused)
    monkeypatch.setattr(stokvel_contract, "is_finalisable", fake.is_finalisable)
    monkeypatch.setattr(stokvel_contract, "finalise", fake.finalise)
    monkeypatch.setattr(stokvel_contract, "round_finalised", fake.round_finalised)
    monkeypatch.setattr(evm_service, "wait_for_receipt", fake.wait_for_receipt)
    return fake


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(
        stokvel_release.queue_service,
        "enqueue_release_pool",
        lambda cycle_id, round_: calls.append((cycle_id, round_)),
    )
    return calls


def _pay(session_factory, vault, round_: int, position: int) -> list[int]:
    """The member at `position` pays `round_`: on-chain, then confirmed in the
    database as `confirm_contribution` would. The rounds the payment released
    on-chain (the event sync records those)."""
    released = vault.contribute(round_)
    member_id = vault.cycle["members"][position]
    with session_factory() as session:
        row = session.scalar(
            select(StokvelContribution).where(
                StokvelContribution.cycle_id == vault.cycle["id"],
                StokvelContribution.round == round_,
                StokvelContribution.member_id == member_id,
            )
        )
        if row is None:
            row = StokvelContribution(
                cycle_id=vault.cycle["id"],
                round=round_,
                member_id=member_id,
                amount_token=CONTRIBUTION,
                amount_fiat=FIAT,
            )
            session.add(row)
        row.status = STATUS_CONFIRMED
        row.evm_tx_hash = "0x" + uuid.uuid4().hex * 2
        row.block_number = BLOCK
        row.confirmed_at = vault.now
        session.commit()
    return released


def _pay_everything(session_factory, vault) -> None:
    for round_ in (0, 1):
        for position in (0, 1):
            assert _pay(session_factory, vault, round_, position) == []


def _deliver(queued) -> list[str]:
    """Run every queued `release_pool`, as a worker would, and clear the queue."""
    outcomes = [release_pool(cycle_id, round_) for cycle_id, round_ in queued]
    queued.clear()
    return outcomes


# --- The ticket's three cases --------------------------------------------------


def test_a_round_paid_early_is_released_only_once_its_payout_time_passes(
    session_factory, cycle, vault, queued
):
    """Everyone paid both rounds early, so no payment released anything. The
    last round of a cycle is always released this way when paid on time."""
    _fund(session_factory, cycle, 2 * POOL)
    _pay_everything(session_factory, vault)

    assert release_due_rounds() == 0
    assert queued == []
    assert vault.asked == []

    vault.now = PAYOUT_TIMES[0]
    assert release_due_rounds() == 1
    assert queued == [(str(cycle["id"]), 0)]
    assert _deliver(queued) == ["released"]
    assert _payouts(session_factory) == [(0, "released", _finalise_hash(0), BLOCK)]

    # Round 1's payout time has not passed.
    assert release_due_rounds() == 0

    vault.now = PAYOUT_TIMES[1] + timedelta(seconds=1)
    assert release_due_rounds() == 1
    assert _deliver(queued) == ["released"]
    assert _payouts(session_factory) == [
        (0, "released", _finalise_hash(0), BLOCK),
        (1, "released", _finalise_hash(1), BLOCK),
    ]
    assert vault.sent == [0, 1]
    assert len(_release_legs(session_factory)) == 2

    # The cycle is released in full: nothing more to queue.
    vault.now += timedelta(days=30)
    assert release_due_rounds() == 0


def test_a_round_whose_last_payment_comes_after_its_payout_time_is_released_once(
    session_factory, cycle, vault, queued
):
    """Round 0 is paid, but its release waits on round 1, which one member pays
    late. That payment releases round 0 itself; the beat never sends a second
    release, whether or not the sync has recorded it yet."""
    _fund(session_factory, cycle, POOL)
    for position in (0, 1):
        _pay(session_factory, vault, 0, position)
    _pay(session_factory, vault, 1, 0)
    vault.now = PAYOUT_TIMES[0] + timedelta(hours=6)

    # Blocked on round 1: never put to the contract.
    assert release_due_rounds() == 0
    assert vault.asked == []

    assert _pay(session_factory, vault, 1, 1) == [0]

    # The sync has not recorded the release yet: the contract says it is done.
    assert release_due_rounds() == 0
    assert vault.asked == [0]

    _record(session_factory, cycle, 0, tx_hash=CONTRIBUTE_HASH)
    assert release_due_rounds() == 0
    assert queued == []
    assert vault.sent == []
    assert _payouts(session_factory) == [(0, "released", CONTRIBUTE_HASH, BLOCK)]
    assert len(_release_legs(session_factory)) == 1


def test_a_double_trigger_releases_the_round_once(
    session_factory, cycle, vault, queued
):
    """Two beat runs before a worker picks either up, and an Administrator's
    manual finalise (R3-10) on top: one `finalise`, one credit."""
    _fund(session_factory, cycle, 2 * POOL)
    _pay_everything(session_factory, vault)
    vault.now = PAYOUT_TIMES[0] + timedelta(minutes=1)

    assert release_due_rounds() == 1
    assert release_due_rounds() == 1
    queued.append((str(cycle["id"]), 0))  # the Administrator's
    before = _balances(session_factory, cycle)

    assert _deliver(queued) == ["released", "already_released", "already_released"]

    assert vault.sent == [0]
    assert _payouts(session_factory) == [(0, "released", _finalise_hash(0), BLOCK)]
    assert len(_release_legs(session_factory)) == 1
    after = _balances(session_factory, cycle)
    assert after["stokvel"] == before["stokvel"] - POOL
    assert release_due_rounds() == 0


# --- What the beat leaves alone -------------------------------------------------


def test_one_round_per_cycle_is_queued_each_run(session_factory, cycle, vault, queued):
    """Both rounds are overdue (the worker was down, say). Rounds release in
    order, so the beat queues the next one and the one after on its next run."""
    _fund(session_factory, cycle, 2 * POOL)
    _pay_everything(session_factory, vault)
    vault.now = PAYOUT_TIMES[1] + timedelta(days=1)

    assert release_due_rounds() == 1
    assert queued == [(str(cycle["id"]), 0)]
    _deliver(queued)

    assert release_due_rounds() == 1
    assert queued == [(str(cycle["id"]), 1)]


def test_a_paused_contract_queues_nothing(
    session_factory, cycle, vault, queued, caplog
):
    _pay_everything(session_factory, vault)
    vault.now = PAYOUT_TIMES[0]
    vault.is_paused = True

    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_release"):
        assert release_due_rounds() == 0

    assert queued == []
    assert vault.asked == []
    assert "event=stokvel.release_sweep_paused" in caplog.text

    vault.is_paused = False
    assert release_due_rounds() == 1


def test_cycles_not_registered_or_closed_are_not_checked(
    session_factory, cycle, vault, queued
):
    _pay_everything(session_factory, vault)
    vault.now = PAYOUT_TIMES[0]
    with session_factory() as session:
        session.get(StokvelCycle, cycle["id"]).registered_at = None
        session.commit()
    assert release_due_rounds() == 0

    with session_factory() as session:
        row = session.get(StokvelCycle, cycle["id"])
        row.registered_at = datetime.now(UTC)
        row.status = StokvelCycleStatus.CLOSED.value
        row.closed_at = datetime.now(UTC)
        session.commit()
    assert release_due_rounds() == 0
    assert vault.asked == []


def test_a_claimed_payout_is_left_to_its_delivery(
    session_factory, cycle, vault, queued, caplog
):
    """A `release_pool` has the payout: it is not queued again, and a claim held
    past the stuck threshold with no hash stored is logged for a person."""
    _pay_everything(session_factory, vault)
    vault.now = PAYOUT_TIMES[0] + timedelta(minutes=5)
    with session_factory() as session:
        payout = ensure_payout(session, cycle["id"], 0)
        payout.release_status = "processing"
        payout.updated_at = vault.now
        session.commit()

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_release"):
        assert release_due_rounds() == 0
    assert "event=stokvel.release_sweep_stuck" not in caplog.text

    vault.now += timedelta(seconds=Config.STOKVEL_RELEASE_INTERVAL_SECONDS + 1)
    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_release"):
        assert release_due_rounds() == 0
    assert "event=stokvel.release_sweep_stuck" not in caplog.text

    vault.now += timedelta(seconds=Config.STOKVEL_RELEASE_STUCK_LOG_SECONDS)
    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_release"):
        assert release_due_rounds() == 0
    assert "event=stokvel.release_sweep_stuck" in caplog.text
    assert queued == []
    assert vault.asked == []


def test_a_payout_whose_send_gave_up_is_queued_again(
    session_factory, cycle, vault, queued
):
    """`release_pool` spent its retries without sending and left the payout
    `pending`: the next run asks again."""
    _pay_everything(session_factory, vault)
    vault.now = PAYOUT_TIMES[0]
    with session_factory() as session:
        ensure_payout(session, cycle["id"], 0)
        session.commit()

    assert release_due_rounds() == 1
    assert queued == [(str(cycle["id"]), 0)]


def test_a_failed_read_or_enqueue_is_logged_and_tried_next_run(
    session_factory, cycle, vault, monkeypatch, caplog
):
    _pay_everything(session_factory, vault)
    vault.now = PAYOUT_TIMES[0]

    vault.read_error = ConnectionError("rpc down")
    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_release"):
        assert release_due_rounds() == 0
    assert "event=stokvel.release_sweep_check_failed" in caplog.text

    vault.read_error = None

    def down(cycle_id, round_):
        raise ConnectionError("broker down")

    monkeypatch.setattr(stokvel_release.queue_service, "enqueue_release_pool", down)
    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_release"):
        assert release_due_rounds() == 0
    assert "event=stokvel.release_sweep_enqueue_failed" in caplog.text


# --- Wiring and the contract wrapper -----------------------------------------


def test_the_scheduled_release_is_on_the_beat():
    assert release_due_rounds.name == "stokvel.release_due_rounds"
    assert release_due_rounds.name in celery.tasks
    [entry] = [
        entry
        for entry in celery.conf.beat_schedule.values()
        if entry["task"] == release_due_rounds.name
    ]
    assert entry["schedule"].run_every == timedelta(
        seconds=Config.STOKVEL_RELEASE_INTERVAL_SECONDS
    )


def test_is_finalisable_reads_the_packed_stokvel_id_and_round(monkeypatch):
    calls = []

    class Functions:
        def isFinalisable(self, stokvel_id, round_):  # noqa: N802 (the ABI's name)
            calls.append((stokvel_id, round_))
            return type("Call", (), {"call": lambda self: True})()

    monkeypatch.setattr(
        stokvel_contract,
        "vault",
        lambda w3: type("Vault", (), {"functions": Functions()})(),
    )
    stokvel_id = uuid.uuid4()

    assert stokvel_contract.is_finalisable(stokvel_id, 1, w3=W3) is True
    assert calls == [(stokvel_id.bytes + bytes(16), 1)]
