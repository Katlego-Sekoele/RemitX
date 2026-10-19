"""The event sync (R2-13, #235): `stokvel.sync_events` and `stokvel_sync`.

Same conventions as test_worker_stokvel_contribution.py, whose fixtures this
reuses: the task runs against a scratch SQLite file with the chain faked.
`stokvel_contract.fetch_events` returns events from a list, and the client's
`eth.block_number` is the chain head.

The ticket's "done when": replaying the same events leaves the database
unchanged.
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from hexbytes import HexBytes
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_sync_state import StokvelSyncState
from remitx_api.models.orm.transaction import STATUS_CONFIRMED, Transaction
from remitx_worker import evm_service, stokvel_contract, stokvel_sync
from remitx_worker.stokvel_contract import ContractEvent
from remitx_worker.stokvel_tasks import (
    confirm_contribution,
    submit_contribution,
    sync_events,
)
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from tests.kyc_helpers import make_user
from tests.test_worker_stokvel_contribution import (
    BLOCK,
    CONTRIBUTION,
    FEE,
    FIAT,
    TX_HASH,
    W3,
    chain,
    enqueued,
    pending,
    session_factory,
)
from web3 import Web3

CONTRACT = "0x2f240705314BB79780522635eA47d20072CB8Fe1"
START = 100
EVENT_HASH = "0x" + "e1" * 32


class FakeLogs:
    """The vault's events on a fake chain: `events` in any order, and a
    head. `fetch_events` filters by block as the real one does, and records
    each range asked for."""

    def __init__(self):
        self.events: list[ContractEvent] = []
        self.head = START + 50
        self.ranges: list[tuple[int, int]] = []
        self.fail: BaseException | None = None
        self.before_return = None

    def fetch_events(self, from_block, to_block, w3):
        self.ranges.append((from_block, to_block))
        if self.fail is not None:
            raise self.fail
        if self.before_return is not None:
            self.before_return()
        return sorted(
            (e for e in self.events if from_block <= e.block_number <= to_block),
            key=lambda e: (e.block_number, e.log_index),
        )


@pytest.fixture
def logs(session_factory, monkeypatch):
    fake = FakeLogs()
    monkeypatch.setattr(stokvel_contract, "fetch_events", fake.fetch_events)
    monkeypatch.setattr(
        evm_service,
        "get_web3",
        lambda: SimpleNamespace(eth=SimpleNamespace(block_number=fake.head)),
    )
    monkeypatch.setenv("STOKVEL_CONTRACT_ADDRESS", CONTRACT)
    monkeypatch.setenv("STOKVEL_SYNC_START_BLOCK", str(START))
    monkeypatch.setenv("STOKVEL_SYNC_CONFIRMATIONS", "0")
    monkeypatch.setenv("STOKVEL_SYNC_BLOCK_RANGE", "10")
    monkeypatch.setenv("STOKVEL_SYNC_MAX_RANGES", "10")
    return fake


def _ids(session_factory, pending):
    with session_factory() as session:
        row = session.get(StokvelContribution, uuid.UUID(pending["id"]))
        cycle = session.get(StokvelCycle, row.cycle_id)
        return cycle.stokvel_id, cycle.id, row.member_id


def _event(name, block, *, stokvel_id, log_index=0, tx_hash=EVENT_HASH, **args):
    return ContractEvent(
        name=name,
        args={"id": evm_service.uuid_to_bytes32(stokvel_id), "cycle": 1, **args},
        tx_hash=tx_hash,
        block_number=block,
        log_index=log_index,
    )


def _contribution_made(stokvel_id, member_id, block, **kwargs):
    return _event(
        "ContributionMade",
        block,
        stokvel_id=stokvel_id,
        round=0,
        memberId=evm_service.uuid_to_bytes32(member_id),
        amount=evm_service.to_base_units(CONTRIBUTION),
        **kwargs,
    )


def _cursor(session_factory):
    with session_factory() as session:
        state = session.get(StokvelSyncState, CONTRACT.lower())
        return None if state is None else state.last_processed_block


def _set_cursor(session_factory, block):
    with session_factory() as session:
        state = session.get(StokvelSyncState, CONTRACT.lower())
        state.last_processed_block = block
        session.commit()


def _snapshot(session_factory):
    """Everything the sync may change, to compare before and after."""
    with session_factory() as session:
        return {
            "contributions": sorted(
                (str(c.id), c.status, c.evm_tx_hash, c.block_number, c.confirmed_at)
                for c in session.query(StokvelContribution)
            ),
            "legs": sorted(
                (str(t.tx_id), t.status, t.confirmed_at)
                for t in session.query(Transaction)
            ),
            "balances": sorted(
                (str(a.account_id), a.account_balance) for a in session.query(Account)
            ),
            "cycles": sorted(
                (str(c.id), c.status, c.closed_at) for c in session.query(StokvelCycle)
            ),
        }


def _balances(session_factory, accounts):
    with session_factory() as session:
        return {
            name: session.get(Account, account_id).account_balance
            for name, account_id in accounts.items()
        }


def _submit(pending_id, monkeypatch):
    """`submit_contribution` with the contribution tests' client, which their
    fake chain expects, then the sync's client back."""
    sync_client = evm_service.get_web3
    monkeypatch.setattr(evm_service, "get_web3", lambda: W3)
    submit_contribution(pending_id)
    monkeypatch.setattr(evm_service, "get_web3", sync_client)


# --- ContributionMade --------------------------------------------------------


def test_a_contribution_made_on_chain_is_confirmed_and_settled(
    session_factory,
    pending,
    logs,
):
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_contribution_made(stokvel_id, member_id, START + 3)]

    sync_events()

    with session_factory() as session:
        row = session.get(StokvelContribution, uuid.UUID(pending["id"]))
        assert (row.status, row.evm_tx_hash, row.block_number) == (
            "confirmed",
            EVENT_HASH,
            START + 3,
        )
        assert {session.get(Transaction, leg).status for leg in pending["legs"]} == {
            STATUS_CONFIRMED
        }
    assert _balances(session_factory, pending["accounts"]) == {
        "member": Decimal("5000") - FIAT - FEE,
        "bank": FIAT,
        "revenue": FEE,
        "treasury": Decimal("1000") - CONTRIBUTION,
        "stokvel": CONTRIBUTION,
    }


def test_replaying_the_same_events_leaves_the_database_unchanged(
    session_factory, pending, logs, caplog
):
    """The ticket's "done when". Every event type, read twice."""
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [
        _contribution_made(stokvel_id, member_id, START + 3),
        _event(
            "RoundFinalised",
            START + 3,
            stokvel_id=stokvel_id,
            log_index=1,
            round=0,
            memberId=evm_service.uuid_to_bytes32(member_id),
            pool=10**20,
        ),
        _event("CycleClosed", START + 4, stokvel_id=stokvel_id),
    ]
    sync_events()
    after_first = _snapshot(session_factory)

    _set_cursor(session_factory, START - 1)  # read the same blocks again
    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_sync"):
        sync_events()

    assert _snapshot(session_factory) == after_first
    assert "unmatched" not in caplog.text


def test_a_contribution_the_worker_already_confirmed_is_not_credited_again(
    session_factory, pending, enqueued, chain, logs, monkeypatch, caplog
):
    _submit(pending["id"], monkeypatch)
    confirm_contribution(*enqueued[0])
    after_confirm = _snapshot(session_factory)
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [
        _contribution_made(stokvel_id, member_id, BLOCK + 1, tx_hash=TX_HASH)
    ]
    logs.head = BLOCK + 10
    monkeypatch.setenv("STOKVEL_SYNC_START_BLOCK", str(BLOCK))

    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_sync"):
        sync_events()

    assert _snapshot(session_factory) == after_confirm
    # Recognised as already recorded, not flagged as a mismatch.
    assert "sync_contribution_unmatched" not in caplog.text


def test_the_event_confirms_a_contribution_whose_confirmation_was_lost(
    session_factory, pending, enqueued, chain, logs, monkeypatch
):
    """The receipt was seen but the confirm message was lost: the
    contribution sits processing with its hash, and the event settles it."""
    _submit(pending["id"], monkeypatch)  # its confirm never runs
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [
        _contribution_made(stokvel_id, member_id, START + 1, tx_hash=TX_HASH)
    ]

    sync_events()

    with session_factory() as session:
        row = session.get(StokvelContribution, uuid.UUID(pending["id"]))
        assert (row.status, row.evm_tx_hash) == ("confirmed", TX_HASH)


def test_a_contribution_the_database_failed_is_flagged_not_changed(
    session_factory,
    pending,
    logs,
    caplog,
):
    confirm_contribution(pending["id"], None, None, "reverted")
    before = _snapshot(session_factory)
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_contribution_made(stokvel_id, member_id, START + 1)]

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_sync"):
        sync_events()

    assert _snapshot(session_factory) == before
    assert "event=stokvel.sync_contribution_unmatched" in caplog.text


def test_events_for_stokvels_this_database_lacks_are_skipped(
    session_factory,
    pending,
    logs,
):
    """The contract is shared, so other backends' stokvels show up too."""
    before = _snapshot(session_factory)
    other = uuid.uuid4()
    logs.events = [
        _contribution_made(other, uuid.uuid4(), START + 1),
        _event("CycleClosed", START + 2, stokvel_id=other),
        ContractEvent(
            "CycleClosed",
            {"id": b"\x01" * 32, "cycle": 1},  # not a packed UUID
            EVENT_HASH,
            START + 3,
            0,
        ),
    ]

    sync_events()

    assert _snapshot(session_factory) == before
    assert _cursor(session_factory) == logs.head


# --- CycleClosed and RoundFinalised -----------------------------------------


def test_cycle_closed_closes_the_cycle_once(
    session_factory,
    pending,
    logs,
):
    stokvel_id, cycle_id, _member_id = _ids(session_factory, pending)
    logs.events = [_event("CycleClosed", START + 2, stokvel_id=stokvel_id)]

    sync_events()

    with session_factory() as session:
        cycle = session.get(StokvelCycle, cycle_id)
        assert cycle.status == "closed"
        assert cycle.closed_at is not None
    session = session_factory()
    assert (
        stokvel_sync.apply_event(session, logs.events[0])
        == stokvel_sync.ALREADY_RECORDED
    )
    session.close()


def test_round_finalised_is_only_noted_until_the_release_task_exists(
    session_factory,
    pending,
    logs,
    caplog,
):
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    before = _snapshot(session_factory)
    logs.events = [
        _event(
            "RoundFinalised",
            START + 2,
            stokvel_id=stokvel_id,
            round=0,
            memberId=evm_service.uuid_to_bytes32(member_id),
            pool=2 * 10**20,
        )
    ]

    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_sync"):
        sync_events()

    assert _snapshot(session_factory) == before
    assert "event=stokvel.round_finalised" in caplog.text


# --- The cursor --------------------------------------------------------------


def test_the_cursor_starts_at_the_start_block_and_reads_in_ranges(
    session_factory,
    logs,
):
    logs.head = START + 24

    assert sync_events() == f"synced to {START + 24}"

    assert logs.ranges == [
        (START, START + 9),
        (START + 10, START + 19),
        (START + 20, START + 24),
    ]
    assert _cursor(session_factory) == START + 24


def test_it_stays_behind_the_head_and_carries_on_from_the_cursor(
    session_factory,
    logs,
    monkeypatch,
):
    monkeypatch.setenv("STOKVEL_SYNC_CONFIRMATIONS", "5")
    logs.head = START + 14

    sync_events()
    assert _cursor(session_factory) == START + 9

    logs.head = START + 20
    logs.ranges.clear()
    sync_events()
    assert logs.ranges == [(START + 10, START + 15)]
    assert _cursor(session_factory) == START + 15


def test_a_run_reads_at_most_the_configured_ranges(
    session_factory,
    logs,
    monkeypatch,
):
    monkeypatch.setenv("STOKVEL_SYNC_MAX_RANGES", "2")
    logs.head = START + 100

    sync_events()

    assert len(logs.ranges) == 2
    assert _cursor(session_factory) == START + 19


def test_up_to_date_reads_nothing(session_factory, logs):
    logs.head = START - 1

    sync_events()

    assert logs.ranges == []
    assert _cursor(session_factory) is None


def test_a_failure_while_applying_keeps_the_cursor_and_the_range_together(
    session_factory,
    pending,
    logs,
    monkeypatch,
):
    """Two events in one range; the second raises. The first is rolled back
    with the cursor, so the next run reads the whole range again."""
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [
        _contribution_made(stokvel_id, member_id, START + 1),
        _event("CycleClosed", START + 2, stokvel_id=stokvel_id),
    ]
    before = _snapshot(session_factory)
    real_apply = stokvel_sync.apply_event

    def crash_on_cycle_closed(session, event):
        if event.name == "CycleClosed":
            raise RuntimeError("worker died")
        return real_apply(session, event)

    monkeypatch.setattr(stokvel_sync, "apply_event", crash_on_cycle_closed)

    with pytest.raises(RuntimeError):
        sync_events()

    assert _snapshot(session_factory) == before
    assert _cursor(session_factory) is None

    monkeypatch.setattr(stokvel_sync, "apply_event", real_apply)
    sync_events()
    with session_factory() as session:
        assert (
            session.get(StokvelContribution, uuid.UUID(pending["id"])).status
            == "confirmed"
        )


def test_an_rpc_error_leaves_the_cursor_for_the_next_run(
    session_factory,
    logs,
    caplog,
):
    logs.fail = ConnectionError("RPC down")

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    assert _cursor(session_factory) is None
    assert "event=stokvel.sync_rpc_error" in caplog.text


def test_a_run_that_finds_the_cursor_moved_stops_without_applying(
    session_factory,
    pending,
    logs,
):
    """Two runs overlap: while this one reads the chain, the other moves the
    cursor. This one applies nothing and stops."""
    sync_events()  # creates the cursor at the head
    head = logs.head
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_contribution_made(stokvel_id, member_id, head + 1)]
    logs.head = head + 5
    logs.before_return = lambda: _set_cursor(session_factory, head + 5)
    before = _snapshot(session_factory)

    sync_events()

    assert _snapshot(session_factory) == before
    assert _cursor(session_factory) == head + 5


@pytest.mark.parametrize("cursor_exists", [False, True])
def test_a_constraint_failure_while_applying_is_raised_not_called_a_race(
    session_factory, pending, logs, caplog, cursor_exists
):
    """A CHECK violation from applying an event is a real fault: it must
    fail the run loudly, not be mistaken for another run creating the cursor
    and swallowed (#346 review). The cursor stays put, so nothing is lost."""
    if cursor_exists:
        sync_events()  # an empty run creates the cursor at the head
        logs.ranges.clear()
    start_cursor = _cursor(session_factory)

    def empty_the_members_account():
        # The member can no longer cover the contribution's legs, so settling
        # it breaks accounts_user_balance_nonneg.
        with session_factory() as session:
            session.get(Account, pending["accounts"]["member"]).account_balance = 0
            session.commit()

    empty_the_members_account()
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    block = (start_cursor or START - 1) + 1
    logs.events = [_contribution_made(stokvel_id, member_id, block)]
    logs.head = block

    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_tasks"):
        with pytest.raises(IntegrityError):
            sync_events()

    assert "sync_raced" not in caplog.text
    assert _cursor(session_factory) == start_cursor
    with session_factory() as session:
        assert (
            session.get(StokvelContribution, uuid.UUID(pending["id"])).status
            == "pending"
        )


def test_a_cursor_another_run_just_created_is_a_quiet_race(
    session_factory, pending, logs, caplog
):
    """Two first runs: the other creates the cursor between this run's read
    and its insert. This one stops and applies nothing."""
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_contribution_made(stokvel_id, member_id, START + 1)]

    def other_run_creates_the_cursor():
        with session_factory() as session:
            session.add(
                StokvelSyncState(id=CONTRACT.lower(), last_processed_block=START + 1)
            )
            session.commit()

    logs.before_return = other_run_creates_the_cursor
    before = _snapshot(session_factory)

    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    assert "event=stokvel.sync_raced" in caplog.text
    assert _snapshot(session_factory) == before
    assert _cursor(session_factory) == START + 1


def test_a_contribution_confirmed_meanwhile_is_reported_as_already_recorded(
    session_factory, pending, monkeypatch, caplog
):
    """`confirm_contribution` wins between the sync's read and its guarded
    update: `record_mined` changes nothing, and the sync must not report it
    as confirmed by the event."""
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    monkeypatch.setattr(stokvel_sync, "record_mined", lambda *args: None)

    session = session_factory()
    try:
        with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_sync"):
            outcome = stokvel_sync.apply_event(
                session, _contribution_made(stokvel_id, member_id, START + 1)
            )
    finally:
        session.close()

    assert outcome == stokvel_sync.ALREADY_RECORDED
    assert "sync_contribution_confirmed" not in caplog.text


def test_without_a_contract_address_nothing_is_read(
    session_factory,
    logs,
    monkeypatch,
):
    monkeypatch.setenv("STOKVEL_CONTRACT_ADDRESS", "")

    assert sync_events() == "skipped"
    assert logs.ranges == []


# --- Reading and decoding the chain -----------------------------------------


def test_fetch_events_asks_for_the_three_events_and_decodes_them_in_order(
    monkeypatch,
):
    """Offline: a real web3 contract object decodes hand-built logs."""
    from eth_abi import encode

    w3 = Web3()
    asked = []
    stokvel_id, member_id = uuid.uuid4(), uuid.uuid4()
    topics = {
        name: stokvel_contract._EVENT_TOPICS[name]
        for name in stokvel_contract.SYNCED_EVENTS
    }

    def log(topic, extra_topics, data, block, index):
        return {
            "address": CONTRACT,
            "topics": [HexBytes(topic), *[HexBytes(t) for t in extra_topics]],
            "data": HexBytes(data),
            "blockNumber": block,
            "transactionHash": HexBytes(bytes([block]) * 32),
            "logIndex": index,
            "blockHash": HexBytes(b"\x00" * 32),
            "transactionIndex": 0,
            "removed": False,
        }

    sid = evm_service.uuid_to_bytes32(stokvel_id)
    mid = evm_service.uuid_to_bytes32(member_id)
    raw = [
        log(topics["CycleClosed"], [sid], encode(["uint32"], [1]), 9, 0),
        log(
            topics["ContributionMade"],
            [sid, mid],
            encode(["uint32", "uint8", "uint256"], [1, 2, 10**20]),
            7,
            1,
        ),
        log(
            topics["RoundFinalised"],
            [sid, mid],
            encode(["uint32", "uint8", "uint256"], [1, 1, 3 * 10**20]),
            7,
            0,
        ),
        log(Web3.keccak(text="Paused(address)"), [], b"", 8, 0),  # not ours
    ]

    def get_logs(params):
        asked.append(params)
        return raw

    monkeypatch.setattr(w3.eth, "get_logs", get_logs)
    monkeypatch.setattr(
        stokvel_contract,
        "vault",
        lambda w3_: w3_.eth.contract(address=CONTRACT, abi=stokvel_contract.VAULT_ABI),
    )

    events = stokvel_contract.fetch_events(5, 9, w3)

    assert asked[0]["fromBlock"] == 5 and asked[0]["toBlock"] == 9
    assert sorted(asked[0]["topics"][0]) == sorted(topics.values())
    assert [(e.name, e.block_number, e.log_index) for e in events] == [
        ("RoundFinalised", 7, 0),
        ("ContributionMade", 7, 1),
        ("CycleClosed", 9, 0),
    ]
    made = events[1]
    assert evm_service.bytes32_to_uuid(made.args["id"]) == stokvel_id
    assert evm_service.bytes32_to_uuid(made.args["memberId"]) == member_id
    assert (made.args["cycle"], made.args["round"], made.args["amount"]) == (
        1,
        2,
        10**20,
    )
    assert made.tx_hash == "0x" + "07" * 32


def test_bytes32_ids_unpack_to_uuids_and_reject_foreign_ones():
    value = uuid.uuid4()
    assert evm_service.bytes32_to_uuid(evm_service.uuid_to_bytes32(value)) == value
    assert evm_service.bytes32_to_uuid(b"\x01" * 32) is None
    assert evm_service.bytes32_to_uuid(b"\x01" * 16) is None


def test_sync_state_timestamps_are_set(session_factory, logs):
    sync_events()
    with session_factory() as session:
        state = session.get(StokvelSyncState, CONTRACT.lower())
        assert state.updated_at is not None
        assert state.updated_at.replace(tzinfo=UTC) <= datetime.now(UTC)


# --- Row-level security (Postgres) -------------------------------------------


@pytest.mark.postgres
def test_no_customer_session_can_see_or_move_the_cursor(postgres_app):
    """The cursor is the worker's: a customer route's session (bound to a
    user) reads no row and cannot write one."""
    key = f"0x{uuid.uuid4().hex}"
    token = db.open_session()
    try:
        customer = make_user()
        db.session.add(StokvelSyncState(id=key, last_processed_block=5))
        db.session.commit()  # unbound, like the worker

        with bound_row_security_context(customer.id, is_admin_route=False):
            assert (
                db.session.scalar(
                    select(StokvelSyncState).where(StokvelSyncState.id == key)
                )
                is None
            )
            moved = db.session.execute(
                update(StokvelSyncState)
                .where(StokvelSyncState.id == key)
                .values(last_processed_block=999)
            )
            assert moved.rowcount == 0
            db.session.add(StokvelSyncState(id=f"{key}-x", last_processed_block=1))
            with pytest.raises(DBAPIError, match="row-level security"):
                db.session.flush()
        db.session.rollback()

        assert db.session.get(StokvelSyncState, key).last_processed_block == 5
    finally:
        db.close_session(token)
