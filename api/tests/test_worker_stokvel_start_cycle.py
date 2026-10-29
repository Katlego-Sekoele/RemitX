"""The cycle worker tasks (R2-10, #232): `stokvel.start_cycle` and the
`stokvel.register_started_cycles` sweep.

Same conventions as test_worker_stokvel_contribution.py: the tasks are called
directly against a scratch SQLite file, with no broker. The chain is faked
(`stokvel_contract.get_stokvel`, `create_stokvel` and `start_cycle`, and
`evm_service.wait_for_receipt`), so the tests assert on what `start_cycle`
sends, the hash it stores and how it records the cycle. The sweep's
`enqueue_start_cycle` is captured.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import Base, build_engine
from remitx_api.models.orm.account import CURRENCY_ZAR, TYPE_USER, Account
from remitx_api.models.orm.beneficiary import Beneficiary, BeneficiaryRelationship
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_cycle import StokvelCycle, StokvelCycleStatus
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_round import StokvelRound
from remitx_api.models.orm.user import User
from remitx_api.services import queue_service
from remitx_worker import db as worker_db, evm_service, stokvel_contract, stokvel_tasks
from remitx_worker.celery_app import celery
from remitx_worker.stokvel_tasks import register_started_cycles, start_cycle
from sqlalchemy.orm import sessionmaker
from web3.exceptions import ContractCustomError

START_HASH = "0x" + "5c" * 32
CREATE_HASH = "0x" + "c4" * 32
BLOCK = 88
CONTRIBUTION = Decimal("100")  # UCTUSD
W3 = object()  # what the task passes around as its web3 client
_START = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


@pytest.fixture
def session_factory(tmp_path, monkeypatch):
    engine = build_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    worker_db.configure(factory)
    # Nothing here may reach a real RPC.
    monkeypatch.setattr(evm_service, "get_web3", lambda: W3)
    yield factory
    worker_db.configure(None)


@pytest.fixture
def enqueued(monkeypatch):
    """The cycle ids `start_cycle` is queued for (by the sweep)."""
    calls = []
    monkeypatch.setattr(
        stokvel_tasks.queue_service, "enqueue_start_cycle", calls.append
    )
    return calls


class FakeChain:
    """The contract as `start_cycle` sees it. `on_chain` is what `getStokvel`
    answers (None: not registered); `createStokvel` registers it, and a mined
    `startCycle` opens the next cycle. `start_errors` are raised by
    successive `startCycle` calls before signing, `after_signing` after the
    hash is handed over; `receipt` is an exception every wait raises."""

    def __init__(self):
        self.on_chain: stokvel_contract.OnChainStokvel | None = None
        self.creates = []
        # Raised by `createStokvel` after it has registered the stokvel, like
        # a duplicate refused `StokvelExists`
        self.create_refusal: BaseException | None = None
        self.starts = []
        self.start_errors: list[BaseException] = []
        self.before_on_signed = None
        self.after_signing: list[BaseException] = []
        self.sent = []
        self.waits = []
        self.receipt: BaseException | None = None

    def get_stokvel(self, stokvel_id, w3=None):
        assert w3 is W3
        return self.on_chain

    def create_stokvel(self, stokvel_id, contribution, *, on_signed=None, w3=None):
        assert w3 is W3
        self.creates.append((stokvel_id, contribution))
        self.on_chain = stokvel_contract.OnChainStokvel(
            evm_service.to_base_units(contribution), 0, False
        )
        if self.create_refusal is not None:
            raise self.create_refusal
        self.sent.append(CREATE_HASH)
        return CREATE_HASH

    def start_cycle(self, stokvel_id, member_ids, starts, deadlines, payouts, **kw):
        assert kw["w3"] is W3
        self.starts.append((stokvel_id, member_ids, starts, deadlines, payouts))
        if self.start_errors:
            raise self.start_errors.pop(0)
        if self.before_on_signed is not None:
            self.before_on_signed()
        kw["on_signed"](START_HASH)
        if self.after_signing:
            raise self.after_signing.pop(0)
        self.sent.append(START_HASH)
        return START_HASH

    def wait_for_receipt(self, tx_hash, timeout=120, w3=None):
        self.waits.append(tx_hash)
        if self.receipt is not None:
            raise self.receipt
        if tx_hash == START_HASH and self.on_chain is not None:
            self.on_chain = stokvel_contract.OnChainStokvel(
                self.on_chain.contribution, self.on_chain.current_cycle + 1, True
            )
        return {"transactionHash": tx_hash, "status": 1, "blockNumber": BLOCK}


@pytest.fixture
def chain(monkeypatch):
    fake = FakeChain()
    monkeypatch.setattr(stokvel_contract, "get_stokvel", fake.get_stokvel)
    monkeypatch.setattr(stokvel_contract, "create_stokvel", fake.create_stokvel)
    monkeypatch.setattr(stokvel_contract, "start_cycle", fake.start_cycle)
    monkeypatch.setattr(evm_service, "wait_for_receipt", fake.wait_for_receipt)
    return fake


def _user_and_account(session) -> tuple[uuid.UUID, uuid.UUID]:
    user = User(id=uuid.uuid4(), clerk_user_id=f"user_{uuid.uuid4()}")
    user.base_reference = f"cyc{user.id.int}"
    session.add(user)
    session.flush()
    account = Account(
        account_id=uuid.uuid4(),
        user_id=user.id,
        type=TYPE_USER,
        reference=f"{uuid.uuid4()}-{CURRENCY_ZAR}",
        account_currency=CURRENCY_ZAR,
        account_balance=Decimal("0"),
        label=f"user {uuid.uuid4().hex[:6]}",
    )
    session.add(account)
    session.flush()
    return user.id, account.account_id


@pytest.fixture
def started(session_factory):
    """A cycle the API has just started: three members, locked in payout
    order (the third joined first, to show the order is the position, not
    the join), three rounds, and a former member's unlocked row."""
    with session_factory() as session:
        people = [_user_and_account(session) for _ in range(4)]
        stokvel = Stokvel(
            organiser_user_id=people[0][0],
            name="Savings club",
            currency=CURRENCY_ZAR,
            contribution_amount=CONTRIBUTION,
        )
        session.add(stokvel)
        session.flush()
        members = []
        for user_id, account_id in people:
            member = StokvelMember(
                stokvel_id=stokvel.id, user_id=user_id, account_id=account_id
            )
            session.add(member)
            session.flush()
            members.append(member)
        members[3].left_at = datetime.now(UTC)
        cycle = StokvelCycle(
            stokvel_id=stokvel.id,
            cycle_number=1,
            status=StokvelCycleStatus.ACTIVE.value,
            total_rounds=3,
            current_round=0,
            started_at=datetime.now(UTC),
        )
        session.add(cycle)
        session.flush()
        stokvel.current_cycle_id = cycle.id
        order = [members[2], members[0], members[1]]
        for position, member in enumerate(order):
            # A locked row needs a beneficiary (locked_is_complete); the
            # worker never reads it.
            beneficiary = Beneficiary(
                sender_user_id=member.user_id,
                linked_user_id=people[3][0],
                payout_currency=CURRENCY_ZAR,
                relationship=BeneficiaryRelationship.PARENT.value,
            )
            session.add(beneficiary)
            session.flush()
            session.add(
                StokvelCycleMember(
                    cycle_id=cycle.id,
                    member_id=member.id,
                    payout_position=position,
                    payout_beneficiary_id=beneficiary.beneficiary_id,
                    payout_currency=CURRENCY_ZAR,
                    locked=True,
                )
            )
        # The former member's row: unlocked, no position, not in the cycle
        session.add(StokvelCycleMember(cycle_id=cycle.id, member_id=members[3].id))
        for number in range(3):
            start = _START + timedelta(minutes=10 * number)
            session.add(
                StokvelRound(
                    cycle_id=cycle.id,
                    round=number,
                    start_time=start,
                    deadline=start + timedelta(minutes=3),
                    payout_time=start + timedelta(minutes=5),
                )
            )
        session.commit()
        return {
            "cycle_id": str(cycle.id),
            "stokvel_id": stokvel.id,
            "order": [member.id for member in order],
        }


def _cycle(factory, cycle_id) -> StokvelCycle:
    with factory() as session:
        row = session.get(StokvelCycle, uuid.UUID(cycle_id))
        session.expunge(row)
        return row


def _registration(factory, cycle_id):
    """(registered, start_tx_hash, start_block_number)."""
    cycle = _cycle(factory, cycle_id)
    return (
        cycle.registered_at is not None,
        cycle.start_tx_hash,
        cycle.start_block_number,
    )


UNREGISTERED = (False, None, None)


def _expected_times():
    starts = [int((_START + timedelta(minutes=10 * n)).timestamp()) for n in range(3)]
    return starts, [s + 180 for s in starts], [s + 300 for s in starts]


# --- Registering -------------------------------------------------------------


def test_a_new_stokvel_is_created_then_its_cycle_started_and_registered(
    session_factory, started, chain
):
    assert start_cycle(started["cycle_id"]) == "registered"

    assert chain.creates == [(started["stokvel_id"], CONTRIBUTION)]
    starts, deadlines, payouts = _expected_times()
    assert chain.starts == [
        (started["stokvel_id"], started["order"], starts, deadlines, payouts)
    ]
    assert chain.waits == [CREATE_HASH, START_HASH]
    assert _registration(session_factory, started["cycle_id"]) == (
        True,
        START_HASH,
        BLOCK,
    )


def test_a_registered_stokvel_is_not_created_again(session_factory, started, chain):
    """Cycle 2 onwards, or a retry after `createStokvel` was mined."""
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)

    assert start_cycle(started["cycle_id"]) == "registered"

    assert chain.creates == []
    assert len(chain.starts) == 1


def test_a_cycle_already_open_on_chain_is_recorded_without_sending(
    session_factory, started, chain, caplog
):
    """An earlier delivery's `startCycle` was mined but its hash was lost."""
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 1, True)

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        assert start_cycle(started["cycle_id"]) == "registered"

    assert chain.sent == []
    assert "event=stokvel.cycle_already_open" in caplog.text
    assert _registration(session_factory, started["cycle_id"]) == (True, None, None)


def test_a_duplicate_that_finds_the_cycle_open_leaves_it_to_the_hash_owner(
    session_factory, started, chain
):
    """Claire's race (#348): one delivery's `startCycle` is mined but not yet
    recorded when a duplicate reads the chain. The duplicate must not record
    the cycle without the block; the hash owner records it."""
    with session_factory() as session:
        cycle = session.get(StokvelCycle, uuid.UUID(started["cycle_id"]))
        cycle.start_tx_hash = START_HASH
        session.commit()
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 1, True)

    # The duplicate, as it would be after reading no stored hash
    assert (
        stokvel_tasks._record_registered(uuid.UUID(started["cycle_id"]), None, None)
        is False
    )
    assert _registration(session_factory, started["cycle_id"]) == (
        False,
        START_HASH,
        None,
    )

    # The hash owner (or its redelivery) still records its block
    assert start_cycle(started["cycle_id"]) == "registered"
    assert _registration(session_factory, started["cycle_id"]) == (
        True,
        START_HASH,
        BLOCK,
    )


def test_a_redelivery_waits_on_the_stored_hash_and_never_starts_twice(
    session_factory, started, chain
):
    """A redelivery after the hash was stored but before the cycle was
    recorded (the task died while waiting)."""
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.receipt = TimeoutError("no receipt yet")
    with pytest.raises(TimeoutError):
        start_cycle(started["cycle_id"])  # direct call: the retry re-raises
    chain.receipt = None
    chain.waits.clear()

    assert start_cycle(started["cycle_id"]) == "registered"

    assert chain.sent.count(START_HASH) == 1
    assert len(chain.starts) == 1
    assert chain.waits == [START_HASH]


def test_a_registered_cycle_is_skipped(session_factory, started, chain):
    start_cycle(started["cycle_id"])

    assert start_cycle(started["cycle_id"]) == "skipped"
    assert len(chain.starts) == 1


def test_a_mined_start_whose_record_fails_is_retried_then_recorded(
    session_factory, started, chain, monkeypatch
):
    """The write after the receipt fails once: the task retries, finds the
    stored hash, and records the cycle without sending again."""
    real = stokvel_tasks._record_registered
    failures = [RuntimeError("database unavailable")]

    def flaky(*args):
        if failures:
            raise failures.pop()
        return real(*args)

    monkeypatch.setattr(stokvel_tasks, "_record_registered", flaky)
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)

    assert start_cycle.apply(args=[started["cycle_id"]]).get() == "registered"
    assert chain.sent == [START_HASH]
    assert _registration(session_factory, started["cycle_id"]) == (
        True,
        START_HASH,
        BLOCK,
    )


def test_a_signed_start_is_not_sent_if_its_hash_cannot_be_stored(
    session_factory, started, chain
):
    """Another delivery stored its hash between this one's read and its
    signing: only one may send."""
    other_hash = "0x" + "aa" * 32
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)

    def other_delivery_stores_first():
        with session_factory() as session:
            cycle = session.get(StokvelCycle, uuid.UUID(started["cycle_id"]))
            cycle.start_tx_hash = other_hash
            session.commit()

    chain.before_on_signed = other_delivery_stores_first

    assert start_cycle(started["cycle_id"]) == "skipped"
    assert START_HASH not in chain.sent
    assert _registration(session_factory, started["cycle_id"]) == (
        False,
        other_hash,
        None,
    )


def test_a_started_cycle_that_is_not_active_is_skipped(session_factory, started, chain):
    with session_factory() as session:
        cycle = session.get(StokvelCycle, uuid.UUID(started["cycle_id"]))
        cycle.status = StokvelCycleStatus.CLOSED.value
        cycle.closed_at = datetime.now(UTC)
        session.commit()

    assert start_cycle(started["cycle_id"]) == "skipped"
    assert chain.starts == []


def test_unknown_and_invalid_ids_are_skipped(session_factory, chain):
    assert start_cycle(str(uuid.uuid4())) == "skipped"
    assert start_cycle("not-a-uuid") == "skipped"


# --- The contract and the database disagree ---------------------------------


@pytest.mark.parametrize(
    "on_chain",
    [
        # This cycle on-chain, but closed (a DB restore, say)
        stokvel_contract.OnChainStokvel(10**20, 1, False),
        # The contract is ahead of the database
        stokvel_contract.OnChainStokvel(10**20, 2, False),
        stokvel_contract.OnChainStokvel(10**20, 2, True),
    ],
    ids=["this-cycle-closed", "ahead-closed", "ahead-open"],
)
def test_cycle_numbers_that_disagree_are_left_for_a_person(
    session_factory, started, chain, caplog, on_chain
):
    chain.on_chain = on_chain

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert start_cycle(started["cycle_id"]) == "needs_person"

    assert "event=stokvel.cycle_start_needs_person" in caplog.text
    assert chain.starts == [] and chain.sent == []
    assert _registration(session_factory, started["cycle_id"]) == UNREGISTERED


def test_a_contribution_that_differs_is_left_for_a_person(
    session_factory, started, chain, caplog
):
    """Starting anyway would charge members 100 in the ledger while every
    `contribute` pulls 10 on-chain."""
    chain.on_chain = stokvel_contract.OnChainStokvel(10 * 10**18, 0, False)

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert start_cycle(started["cycle_id"]) == "needs_person"

    assert "contribution" in caplog.text
    assert chain.starts == [] and chain.sent == []
    assert _registration(session_factory, started["cycle_id"]) == UNREGISTERED


def test_a_later_cycle_of_an_unregistered_stokvel_is_left_for_a_person(
    session_factory, started, chain
):
    with session_factory() as session:
        cycle = session.get(StokvelCycle, uuid.UUID(started["cycle_id"]))
        cycle.cycle_number = 2
        session.commit()

    assert start_cycle(started["cycle_id"]) == "needs_person"
    assert chain.creates == [] and chain.starts == []


# --- Refusals and RPC trouble ------------------------------------------------


def test_a_rule_refusal_is_left_for_a_person(session_factory, started, chain, caplog):
    """The API checks every rule `startCycle` enforces, so a refusal here is
    a fault, not the Organiser's: logged, nothing sent or recorded."""
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.start_errors = [
        stokvel_contract.ContractRefused("InvalidSchedule", "execution reverted")
    ]

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert start_cycle(started["cycle_id"]) == "refused"

    assert "event=stokvel.cycle_start_refused" in caplog.text
    assert "error=InvalidSchedule" in caplog.text
    assert chain.sent == []
    assert _cycle(session_factory, started["cycle_id"]).registered_at is None


def test_a_missing_operator_role_is_retried_then_succeeds(
    session_factory, started, chain
):
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.start_errors = [
        stokvel_contract.ContractRefused("AccessControlUnauthorizedAccount", "x")
    ]

    assert start_cycle.apply(args=[started["cycle_id"]]).get() == "registered"
    assert len(chain.starts) == 2
    assert chain.sent == [START_HASH]


def test_a_refusal_that_outlasts_the_retries_leaves_it_unsent(
    session_factory, started, chain, caplog
):
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.start_errors = [
        stokvel_contract.ContractRefused("AccessControlUnauthorizedAccount", "x")
    ] * (stokvel_tasks.MAX_RETRIES + 1)

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        assert start_cycle.apply(args=[started["cycle_id"]]).get() == "unsent"

    assert caplog.text.count("event=stokvel.cycle_start_retry") == (
        stokvel_tasks.MAX_RETRIES
    )
    assert "event=stokvel.cycle_start_unsent" in caplog.text
    assert chain.sent == []


def test_an_rpc_error_before_signing_retries(session_factory, started, chain):
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.start_errors = [ConnectionError("RPC down")]

    with pytest.raises(ConnectionError):
        start_cycle(started["cycle_id"])  # direct call: the retry re-raises

    assert _cycle(session_factory, started["cycle_id"]).start_tx_hash is None
    assert chain.sent == []


def test_a_refused_send_drops_its_hash_and_retries(session_factory, started, chain):
    """The RPC refused the signed `startCycle`: it can never be mined, so its
    stored hash is cleared for the next attempt's."""
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.after_signing = [
        evm_service.TransactionRejected(START_HASH, Exception("insufficient funds"))
    ]

    assert start_cycle.apply(args=[started["cycle_id"]]).get() == "registered"
    assert len(chain.starts) == 2
    assert chain.sent == [START_HASH]
    assert _registration(session_factory, started["cycle_id"]) == (
        True,
        START_HASH,
        BLOCK,
    )


def test_a_send_that_raises_after_its_hash_is_stored_is_waited_on(
    session_factory, started, chain
):
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.after_signing = [TimeoutError("send timed out")]

    assert start_cycle(started["cycle_id"]) == "registered"
    assert chain.waits == [START_HASH]
    assert _registration(session_factory, started["cycle_id"]) == (
        True,
        START_HASH,
        BLOCK,
    )


def test_a_reverted_start_is_left_for_a_person(session_factory, started, chain, caplog):
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.receipt = evm_service.TransactionReverted("reverted")

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert start_cycle(started["cycle_id"]) == "reverted"

    assert "event=stokvel.cycle_start_reverted" in caplog.text
    assert _registration(session_factory, started["cycle_id"]) == (
        False,
        START_HASH,
        None,
    )


def test_a_create_that_finds_the_stokvel_registered_carries_on(
    session_factory, started, chain
):
    """A duplicate `createStokvel` (an earlier one still unmined when this
    attempt read the chain) is refused `StokvelExists`: fine, it exists."""
    chain.create_refusal = stokvel_contract.ContractRefused("StokvelExists", "x")

    assert start_cycle(started["cycle_id"]) == "registered"
    assert len(chain.creates) == 1
    assert chain.sent == [START_HASH]


def test_a_create_refused_for_another_reason_is_left_for_a_person(
    session_factory, started, chain, caplog, monkeypatch
):
    def refuses(stokvel_id, contribution, *, on_signed=None, w3=None):
        chain.creates.append((stokvel_id, contribution))
        raise stokvel_contract.ContractRefused("ZeroContribution", "reverted")

    monkeypatch.setattr(stokvel_contract, "create_stokvel", refuses)

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert start_cycle(started["cycle_id"]) == "refused"

    assert "error=ZeroContribution" in caplog.text
    assert chain.starts == []


def test_no_receipt_retries_the_same_hash_then_leaves_it_for_a_person(
    session_factory, started, chain, caplog
):
    chain.on_chain = stokvel_contract.OnChainStokvel(10**20, 0, False)
    chain.receipt = TimeoutError("no receipt")

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        result = start_cycle.apply(args=[started["cycle_id"]]).get()

    assert result == "awaiting_receipt"
    assert chain.sent == [START_HASH]  # waited on, never resent
    assert set(chain.waits) == {START_HASH}
    assert "event=stokvel.cycle_start_unconfirmed" in caplog.text
    assert _registration(session_factory, started["cycle_id"]) == (
        False,
        START_HASH,
        None,
    )


# --- Wiring and the contract wrapper -----------------------------------------


def test_the_api_and_the_worker_agree_on_the_task_names():
    assert queue_service.START_CYCLE == start_cycle.name
    assert start_cycle.name in celery.tasks
    assert register_started_cycles.name in celery.tasks


def test_the_sweep_is_on_the_beat():
    tasks = {entry["task"] for entry in celery.conf.beat_schedule.values()}
    assert register_started_cycles.name in tasks


# --- The sweep ----------------------------------------------------------------


def _set_started_at(factory, cycle_id, when):
    with factory() as session:
        cycle = session.get(StokvelCycle, uuid.UUID(cycle_id))
        cycle.started_at = when
        session.commit()


def test_the_sweep_queues_an_unregistered_cycle_once_it_is_old_enough(
    session_factory, started, enqueued, caplog
):
    """The API committed the start but its enqueue was lost."""
    old = datetime.now(UTC) - timedelta(hours=1)
    _set_started_at(session_factory, started["cycle_id"], old)

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        assert register_started_cycles() == 1

    assert enqueued == [started["cycle_id"]]
    assert "event=stokvel.cycle_sweep" in caplog.text


def test_the_sweep_leaves_a_cycle_that_just_started(session_factory, started, enqueued):
    """Its first `start_cycle` is still queued or running."""
    _set_started_at(session_factory, started["cycle_id"], datetime.now(UTC))

    assert register_started_cycles() == 0
    assert enqueued == []


def test_the_sweep_skips_registered_and_closed_cycles(
    session_factory, started, enqueued, chain
):
    old = datetime.now(UTC) - timedelta(hours=1)
    _set_started_at(session_factory, started["cycle_id"], old)
    assert start_cycle(started["cycle_id"]) == "registered"

    assert register_started_cycles() == 0
    assert enqueued == []


def test_a_failed_sweep_enqueue_is_logged_and_the_rest_carry_on(
    session_factory, started, monkeypatch, caplog
):
    def down(cycle_id):
        raise ConnectionError("broker down")

    monkeypatch.setattr(stokvel_tasks.queue_service, "enqueue_start_cycle", down)
    old = datetime.now(UTC) - timedelta(hours=1)
    _set_started_at(session_factory, started["cycle_id"], old)

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert register_started_cycles() == 0

    assert "event=stokvel.cycle_sweep_enqueue_failed" in caplog.text


class _FakeCall:
    def __init__(self, value=None, error=None):
        self.value, self.error = value, error

    def call(self):
        if self.error is not None:
            raise self.error
        return self.value


class _FakeVault:
    def __init__(self):
        self.address = "0xVault"
        self.encoded = []
        self.functions = self
        self.stokvel = _FakeCall((10**20, 1, True))

    def getStokvel(self, stokvel_id):  # noqa: N802 - the contract's name
        return self.stokvel

    def encode_abi(self, name, args):
        self.encoded.append((name, args))
        return f"data:{name}"


@pytest.fixture
def wrapper(monkeypatch):
    vault = _FakeVault()
    sent = []

    def submit(tx, w3=None, *, on_signed=None):
        sent.append(tx)
        if on_signed is not None:
            on_signed(START_HASH)
        return START_HASH

    monkeypatch.setattr(stokvel_contract, "vault", lambda w3: vault)
    monkeypatch.setattr(evm_service, "submit_transaction", submit)
    return {"vault": vault, "sent": sent}


def _error_data(name: str) -> str:
    entry = next(
        entry
        for entry in stokvel_contract.VAULT_ABI
        if entry["type"] == "error" and entry["name"] == name
    )
    return "0x" + stokvel_contract._selector(stokvel_contract._signature(entry))


def test_get_stokvel_reads_the_contract(wrapper):
    assert stokvel_contract.get_stokvel(uuid.uuid4(), w3=W3) == (
        stokvel_contract.OnChainStokvel(10**20, 1, True)
    )


def test_get_stokvel_is_none_for_an_unregistered_stokvel(wrapper):
    data = _error_data("UnknownStokvel")
    wrapper["vault"].stokvel = _FakeCall(error=ContractCustomError(data, data=data))

    assert stokvel_contract.get_stokvel(uuid.uuid4(), w3=W3) is None


def test_get_stokvel_raises_any_other_revert(wrapper):
    data = _error_data("ZeroId")
    wrapper["vault"].stokvel = _FakeCall(error=ContractCustomError(data, data=data))

    with pytest.raises(ContractCustomError):
        stokvel_contract.get_stokvel(uuid.uuid4(), w3=W3)


def test_create_stokvel_sends_the_packed_id_and_base_units(wrapper):
    stokvel_id = uuid.uuid4()

    assert stokvel_contract.create_stokvel(stokvel_id, CONTRIBUTION, w3=W3) == (
        START_HASH
    )
    assert wrapper["vault"].encoded == [
        ("createStokvel", [stokvel_id.bytes + bytes(16), 100 * 10**18])
    ]
    assert wrapper["sent"] == [{"to": "0xVault", "data": "data:createStokvel"}]


def test_start_cycle_sends_members_in_order_and_the_schedule(wrapper):
    stokvel_id, first, second = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    signed = []

    stokvel_contract.start_cycle(
        stokvel_id,
        [first, second],
        [10, 20],
        [11, 21],
        [12, 22],
        on_signed=signed.append,
        w3=W3,
    )

    assert wrapper["vault"].encoded == [
        (
            "startCycle",
            [
                stokvel_id.bytes + bytes(16),
                [first.bytes + bytes(16), second.bytes + bytes(16)],
                [10, 20],
                [11, 21],
                [12, 22],
            ],
        )
    ]
    assert signed == [START_HASH]


def test_the_abi_has_the_functions_the_wrapper_calls():
    functions = {
        entry["name"]
        for entry in stokvel_contract.VAULT_ABI
        if entry["type"] == "function"
    }
    assert {"getStokvel", "createStokvel", "startCycle"} <= functions
