"""The event sync (R2-13, #235): `stokvel.sync_events` and `stokvel_sync`.

Same conventions as test_worker_stokvel_contribution.py, whose fixtures this
reuses: the task runs against a scratch SQLite file with the chain faked.
`stokvel_contract.fetch_logs` returns logs from a list (already-decoded
events, which the faked `decode_log` passes through, or a raw `BAD_LOG` it
refuses), and the client's `eth.block_number` is the chain head.

The ticket's "done when": replaying the same events leaves the database
unchanged.
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from hexbytes import HexBytes
from remitx_api.db.rls import bound_row_security_context
from remitx_api.extensions import db
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.beneficiary import Beneficiary, BeneficiaryRelationship
from remitx_api.models.orm.stokvel import Stokvel
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_held_event import StokvelHeldEvent
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.stokvel_sync_state import StokvelSyncState
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_STOKVEL_POOL_RELEASE,
    Transaction,
)
from remitx_api.models.orm.user import User
from remitx_api.services import queue_service
from remitx_worker import evm_service, stokvel_contract, stokvel_sync
from remitx_worker.stokvel_contract import ContractEvent
from remitx_worker.stokvel_tasks import (
    confirm_contribution,
    submit_contribution,
    sync_events,
)
from sqlalchemy import select, update
from sqlalchemy.exc import DBAPIError
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


def _raw_log(block, log_index=0):
    """A raw log the faked `decode_log` refuses: what a drifted ABI copy or a
    malformed log looks like to the sync."""
    return {
        "address": CONTRACT,
        "topics": [HexBytes(b"\xab" * 32)],
        "data": HexBytes(b""),
        "blockNumber": block,
        "transactionHash": HexBytes(b"\xbd" * 32),
        "logIndex": log_index,
        "blockHash": HexBytes(b"\x00" * 32),
        "transactionIndex": 0,
    }


class FakeLogs:
    """The vault's logs on a fake chain, in any order, and a head.
    `fetch_logs` filters by block and sorts as the real one does, and records
    each range asked for. `decode_log` passes a `ContractEvent` through and
    refuses a raw log unless `decodes` is set."""

    def __init__(self):
        self.events: list = []
        self.head = START + 50
        self.ranges: list[tuple[int, int]] = []
        self.fail: BaseException | None = None
        self.before_return = None
        self.decodes: ContractEvent | None = None

    @staticmethod
    def _where(log):
        if isinstance(log, ContractEvent):
            return log.block_number, log.log_index
        return log["blockNumber"], log["logIndex"]

    def fetch_logs(self, from_block, to_block, w3):
        self.ranges.append((from_block, to_block))
        if self.fail is not None:
            raise self.fail
        if self.before_return is not None:
            self.before_return()
        return sorted(
            (e for e in self.events if from_block <= self._where(e)[0] <= to_block),
            key=self._where,
        )

    def decode_log(self, log, w3):
        if isinstance(log, ContractEvent):
            return log
        if self.decodes is not None:
            return self.decodes
        raise ValueError("Could not decode the log with the vault ABI")


@pytest.fixture
def payouts_queued(monkeypatch):
    """The payouts the sync queues for R3-05 at the end of a run."""
    queued = []
    monkeypatch.setattr(
        queue_service,
        "enqueue_settle_payout",
        lambda payout_id: queued.append(payout_id),
    )
    return queued


@pytest.fixture
def logs(session_factory, monkeypatch, payouts_queued):
    fake = FakeLogs()
    monkeypatch.setattr(stokvel_contract, "fetch_logs", fake.fetch_logs)
    monkeypatch.setattr(stokvel_contract, "decode_log", fake.decode_log)
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


def _round_finalised(stokvel_id, member_id, block, round_=0, **kwargs):
    return _event(
        "RoundFinalised",
        block,
        stokvel_id=stokvel_id,
        round=round_,
        memberId=evm_service.uuid_to_bytes32(member_id),
        pool=2 * 10**20,
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


def _held(session_factory):
    """(name, reason, resolved) for every held event, in chain order."""
    with session_factory() as session:
        return [
            (row.name, row.reason, row.resolved_at is not None)
            for row in session.scalars(
                select(StokvelHeldEvent).order_by(
                    StokvelHeldEvent.block_number, StokvelHeldEvent.log_index
                )
            )
        ]


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
            "payouts": sorted(
                (
                    str(p.cycle_id),
                    p.round,
                    p.release_status,
                    p.release_tx_hash,
                    p.release_block_number,
                    str(p.release_tx_id),
                )
                for p in session.query(StokvelPayout)
            ),
            "held": sorted(
                (h.tx_hash, h.log_index, h.reason, h.resolved_at is not None)
                for h in session.query(StokvelHeldEvent)
            ),
        }


def _balances(session_factory, accounts):
    with session_factory() as session:
        return {
            name: session.get(Account, account_id).account_balance
            for name, account_id in accounts.items()
        }


def _fund_stokvel(session_factory, pending, amount=CONTRIBUTION):
    """Book `amount` more into the stokvel, as the other members'
    contributions would have: a release takes the whole pool out of
    `STOKVEL`, which can never go below zero."""
    accounts = pending["accounts"]
    with session_factory() as session:
        session.execute(
            update(Account)
            .where(Account.account_id == accounts["treasury"])
            .values(account_balance=Account.account_balance - amount)
        )
        session.execute(
            update(Account)
            .where(Account.account_id == accounts["stokvel"])
            .values(account_balance=Account.account_balance + amount)
        )
        session.commit()


def _members_by_round(session_factory, cycle_id):
    with session_factory() as session:
        return {
            row.payout_position: row.member_id
            for row in session.scalars(
                select(StokvelCycleMember).where(
                    StokvelCycleMember.cycle_id == cycle_id
                )
            )
        }


def _payouts(session_factory):
    """(round, status, hash, block, leg amount) for every payout, by round."""
    with session_factory() as session:
        return [
            (
                p.round,
                p.release_status,
                p.release_tx_hash,
                p.release_block_number,
                None
                if p.release_tx_id is None
                else session.get(Transaction, p.release_tx_id).amount,
            )
            for p in session.scalars(
                select(StokvelPayout).order_by(StokvelPayout.round)
            )
        ]


POOL = 2 * CONTRIBUTION  # two members


def _submit(pending_id, monkeypatch):
    """`submit_contribution` with the contribution tests' client, which their
    fake chain expects, then the sync's client back."""
    sync_client = evm_service.get_web3
    monkeypatch.setattr(evm_service, "get_web3", lambda: W3)
    submit_contribution(pending_id)
    monkeypatch.setattr(evm_service, "get_web3", sync_client)


def _release_every_round(session_factory, pending):
    """Record every round of the cycle as released, as the release task
    (R3-04) will: a `STOKVEL -> Treasury` leg and a released payout each."""
    accounts = pending["accounts"]
    with session_factory() as session:
        row = session.get(StokvelContribution, uuid.UUID(pending["id"]))
        members = session.scalars(
            select(StokvelCycleMember).where(
                StokvelCycleMember.cycle_id == row.cycle_id
            )
        ).all()
        for member in members:
            leg = Transaction(
                tx_id=uuid.uuid4(),
                type=TYPE_STOKVEL_POOL_RELEASE,
                credit_account_id=accounts["stokvel"],
                debit_account_id=accounts["treasury"],
                amount=Decimal("0.01"),
                currency="UCTUSD",
                status=STATUS_CONFIRMED,
            )
            session.add(leg)
            session.flush()
            session.add(
                StokvelPayout(
                    cycle_id=row.cycle_id,
                    round=member.payout_position,
                    member_id=member.member_id,
                    release_status="released",
                    release_tx_hash="0x" + f"{member.payout_position:02x}" * 32,
                    release_block_number=START,
                    release_tx_id=leg.tx_id,
                    released_at=datetime.now(UTC) - timedelta(minutes=1),
                )
            )
        session.commit()


# --- ContributionMade --------------------------------------------------------


def test_a_contribution_made_on_chain_is_confirmed_and_settled(
    session_factory, pending, logs
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
    """The ticket's "done when". Every event type, read twice: the applied
    one is not applied again, and the held ones are not held twice."""
    _fund_stokvel(session_factory, pending)  # the other member's contribution
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [
        _contribution_made(stokvel_id, member_id, START + 3),
        _round_finalised(stokvel_id, member_id, START + 3, log_index=1),
        _event("CycleClosed", START + 4, stokvel_id=stokvel_id),
    ]
    sync_events()
    after_first = _snapshot(session_factory)
    assert [p[:3] for p in _payouts(session_factory)] == [(0, "released", EVENT_HASH)]

    _set_cursor(session_factory, START - 1)  # read the same blocks again
    with caplog.at_level(logging.INFO, logger="remitx_worker"):
        sync_events()

    assert _snapshot(session_factory) == after_first
    assert "reason=failed" not in caplog.text


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

    with caplog.at_level(logging.INFO, logger="remitx_worker"):
        sync_events()

    assert _snapshot(session_factory) == after_confirm
    # Recognised as already recorded, not held for a person.
    assert "reason=failed" not in caplog.text


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


def test_a_different_transaction_hash_is_held_not_written(
    session_factory, pending, enqueued, chain, logs, monkeypatch, caplog
):
    """The worker stored one transaction, the chain recorded another: the
    books must not be moved onto it (#346 review)."""
    _submit(pending["id"], monkeypatch)  # stores TX_HASH, stays processing
    before = _snapshot(session_factory)
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_contribution_made(stokvel_id, member_id, START + 1)]

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    after = _snapshot(session_factory)
    assert after["contributions"] == before["contributions"]
    assert after["balances"] == before["balances"]
    assert _held(session_factory) == [("ContributionMade", "failed", False)]
    assert "stored " + TX_HASH in caplog.text
    assert _cursor(session_factory) == logs.head


def test_a_contribution_the_database_failed_is_held_for_a_person(
    session_factory, pending, logs, caplog
):
    confirm_contribution(pending["id"], None, None, "reverted")
    before = _snapshot(session_factory)
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_contribution_made(stokvel_id, member_id, START + 1)]

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    after = _snapshot(session_factory)
    assert {k: v for k, v in after.items() if k != "held"} == {
        k: v for k, v in before.items() if k != "held"
    }
    assert _held(session_factory) == [("ContributionMade", "failed", False)]
    assert "event=stokvel.sync_event_held reason=failed" in caplog.text


def test_events_for_stokvels_this_database_lacks_are_skipped(
    session_factory, pending, logs
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


# --- RoundFinalised and CycleClosed -----------------------------------------


def test_a_round_finalised_records_the_release_once(
    session_factory, pending, logs, payouts_queued
):
    """R3-04: the payout row is created and released, and the pool moves from
    `STOKVEL` to the Treasury in one confirmed leg. Replaying it books
    nothing twice."""
    _fund_stokvel(session_factory, pending, POOL)
    before = _balances(session_factory, pending["accounts"])
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_round_finalised(stokvel_id, member_id, START + 2)]

    sync_events()

    assert _payouts(session_factory) == [(0, "released", EVENT_HASH, START + 2, POOL)]
    with session_factory() as session:
        payout = session.scalars(select(StokvelPayout)).one()
        leg = session.get(Transaction, payout.release_tx_id)
        assert (leg.type, leg.status) == (TYPE_STOKVEL_POOL_RELEASE, STATUS_CONFIRMED)
        assert (leg.credit_account_id, leg.debit_account_id) == (
            pending["accounts"]["stokvel"],
            pending["accounts"]["treasury"],
        )
        assert payout.member_id == member_id
        assert payout.released_at is not None
        assert payout.remittance_status == "pending"  # R3-05 pays it out
    after = _balances(session_factory, pending["accounts"])
    assert after["stokvel"] == before["stokvel"] - POOL
    assert after["treasury"] == before["treasury"] + POOL
    assert _held(session_factory) == []
    # Then paid out (R3-05): queued once the run has committed the release
    assert payouts_queued == [str(payout.id)]

    _set_cursor(session_factory, START - 1)
    once = _snapshot(session_factory)
    sync_events()
    assert _snapshot(session_factory) == once


def test_a_round_held_before_the_release_existed_is_recorded_on_the_next_run(
    session_factory, pending, logs, monkeypatch, caplog
):
    """Before R3-04 a RoundFinalised was held as waiting. The first run with
    the real handler records it: no round released meanwhile is lost."""
    _fund_stokvel(session_factory, pending, POOL)
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_round_finalised(stokvel_id, member_id, START + 2)]
    real_handler = stokvel_sync._round_finalised
    monkeypatch.setattr(
        stokvel_sync, "_round_finalised", lambda session, event: stokvel_sync.WAITING
    )
    sync_events()
    assert _held(session_factory) == [("RoundFinalised", "waiting", False)]
    assert _cursor(session_factory) == logs.head

    monkeypatch.setattr(stokvel_sync, "_round_finalised", real_handler)
    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    assert _payouts(session_factory) == [(0, "released", EVENT_HASH, START + 2, POOL)]
    assert _held(session_factory) == [("RoundFinalised", "waiting", True)]
    assert "event=stokvel.sync_event_resolved" in caplog.text


def test_the_last_rounds_and_cycle_closed_in_one_transaction_close_the_cycle_at_once(
    session_factory, pending, logs
):
    """A cycle's final contribution, made after the last round's payout
    time, releases the last two rounds and closes the cycle in one
    transaction: both payouts share its hash, and the cycle
    closes in the same run, because each release is recorded before the
    CycleClosed that follows it."""
    _fund_stokvel(session_factory, pending, 2 * POOL)
    stokvel_id, cycle_id, _member_id = _ids(session_factory, pending)
    members = _members_by_round(session_factory, cycle_id)
    logs.events = [
        _round_finalised(stokvel_id, members[0], START + 2, round_=0, log_index=1),
        _round_finalised(stokvel_id, members[1], START + 2, round_=1, log_index=2),
        _event("CycleClosed", START + 2, stokvel_id=stokvel_id, log_index=3),
    ]

    sync_events()

    assert _payouts(session_factory) == [
        (0, "released", EVENT_HASH, START + 2, POOL),
        (1, "released", EVENT_HASH, START + 2, POOL),
    ]
    with session_factory() as session:
        assert session.get(StokvelCycle, cycle_id).status == "closed"
    assert _held(session_factory) == []


def test_a_release_to_a_member_the_round_does_not_pay_is_held_for_a_person(
    session_factory, pending, logs
):
    _fund_stokvel(session_factory, pending, POOL)
    stokvel_id, cycle_id, _member_id = _ids(session_factory, pending)
    members = _members_by_round(session_factory, cycle_id)
    logs.events = [_round_finalised(stokvel_id, members[1], START + 2, round_=0)]
    before = _snapshot(session_factory)

    sync_events()

    assert _held(session_factory) == [("RoundFinalised", "failed", False)]
    after = _snapshot(session_factory)
    assert {k: v for k, v in after.items() if k != "held"} == {
        k: v for k, v in before.items() if k != "held"
    }


def test_a_round_released_with_another_hash_is_held_for_a_person(
    session_factory, pending, logs
):
    _fund_stokvel(session_factory, pending, POOL)
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_round_finalised(stokvel_id, member_id, START + 2)]
    sync_events()
    logs.events = [
        _round_finalised(
            stokvel_id, member_id, START + 3, tx_hash="0x" + "e2" * 32, log_index=0
        )
    ]
    recorded = _payouts(session_factory)
    _set_cursor(session_factory, START - 1)

    sync_events()

    assert _payouts(session_factory) == recorded
    assert _held(session_factory) == [("RoundFinalised", "failed", False)]


def test_a_release_before_its_contributions_are_recorded_waits_for_them(
    session_factory, pending, logs
):
    """`STOKVEL` can never go below zero. A release whose pool is not all
    recorded yet is held, changes nothing, and is recorded by a later run
    once the contributions are in."""
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_round_finalised(stokvel_id, member_id, START + 2)]
    before = _snapshot(session_factory)

    sync_events()

    assert _held(session_factory) == [("RoundFinalised", "failed", False)]
    assert _payouts(session_factory) == []
    assert _snapshot(session_factory)["balances"] == before["balances"]

    _fund_stokvel(session_factory, pending, POOL)
    sync_events()

    assert _payouts(session_factory) == [(0, "released", EVENT_HASH, START + 2, POOL)]
    assert _held(session_factory) == [("RoundFinalised", "failed", True)]


def test_cycle_closed_waits_until_every_payout_is_released(
    session_factory, pending, logs
):
    """The last round's RoundFinalised and CycleClosed share a transaction.
    The cycle stays open until every round's payout is recorded, so it never
    closes with a payout missing, and a new cycle cannot open early."""
    stokvel_id, cycle_id, _member_id = _ids(session_factory, pending)
    logs.events = [_event("CycleClosed", START + 2, stokvel_id=stokvel_id)]

    sync_events()

    with session_factory() as session:
        assert session.get(StokvelCycle, cycle_id).status == "active"
    assert _held(session_factory) == [("CycleClosed", "waiting", False)]

    _release_every_round(session_factory, pending)
    sync_events()

    with session_factory() as session:
        cycle = session.get(StokvelCycle, cycle_id)
        assert cycle.status == "closed"
        assert cycle.closed_at is not None
    assert _held(session_factory) == [("CycleClosed", "waiting", True)]


def test_cycle_closed_with_every_payout_released_closes_once(
    session_factory, pending, logs
):
    _release_every_round(session_factory, pending)
    stokvel_id, cycle_id, _member_id = _ids(session_factory, pending)
    logs.events = [_event("CycleClosed", START + 2, stokvel_id=stokvel_id)]

    sync_events()

    with session_factory() as session:
        assert session.get(StokvelCycle, cycle_id).status == "closed"
    assert _held(session_factory) == []
    session = session_factory()
    try:
        assert (
            stokvel_sync.apply_event(session, logs.events[0])
            == stokvel_sync.ALREADY_RECORDED
        )
    finally:
        session.close()


# --- CycleClosed opens the next cycle (R2-15) -------------------------------


def _lock_with_beneficiaries(session_factory, pending) -> dict[uuid.UUID, uuid.UUID]:
    """Lock the cycle's rows as a start does (R2-10), each with a
    beneficiary: a started cycle's members are its locked rows. Returns each
    member's beneficiary, by member id."""
    chosen = {}
    with session_factory() as session:
        row = session.get(StokvelContribution, uuid.UUID(pending["id"]))
        rows = session.scalars(
            select(StokvelCycleMember).where(
                StokvelCycleMember.cycle_id == row.cycle_id
            )
        ).all()
        linked = _new_user(session)
        for cycle_row in rows:
            member = session.get(StokvelMember, cycle_row.member_id)
            beneficiary = Beneficiary(
                sender_user_id=member.user_id,
                linked_user_id=linked.id,
                payout_currency="ZAR",
                relationship=BeneficiaryRelationship.PARENT.value,
            )
            session.add(beneficiary)
            session.flush()
            cycle_row.payout_beneficiary_id = beneficiary.beneficiary_id
            cycle_row.payout_currency = "ZAR"
            cycle_row.locked = True
            chosen[cycle_row.member_id] = beneficiary.beneficiary_id
        session.commit()
    return chosen


def _new_user(session) -> User:
    suffix = uuid.uuid4().hex[:10]
    user = User(
        clerk_user_id=f"user_{suffix}",
        email=f"{suffix}@example.com",
        first_name="Test",
        base_reference=suffix,
    )
    session.add(user)
    session.flush()
    return user


def _join_mid_cycle(session_factory, stokvel_id) -> uuid.UUID:
    """A member who accepted while the cycle ran: no row in it (R2-08)."""
    with session_factory() as session:
        organiser_row = session.scalars(
            select(StokvelMember).where(StokvelMember.stokvel_id == stokvel_id)
        ).first()
        member = StokvelMember(
            stokvel_id=stokvel_id,
            user_id=_new_user(session).id,
            account_id=organiser_row.account_id,
        )
        session.add(member)
        session.commit()
        return member.id


def _close_cycle(session_factory, pending, logs):
    _release_every_round(session_factory, pending)
    stokvel_id, cycle_id, organiser_member_id = _ids(session_factory, pending)
    logs.events = [_event("CycleClosed", START + 2, stokvel_id=stokvel_id)]
    sync_events()
    return stokvel_id, cycle_id, organiser_member_id


def _rows(session, cycle_id) -> dict[uuid.UUID, StokvelCycleMember]:
    return {
        row.member_id: row
        for row in session.scalars(
            select(StokvelCycleMember).where(StokvelCycleMember.cycle_id == cycle_id)
        )
    }


def test_closing_a_cycle_opens_the_next_with_the_organiser_carried_over(
    session_factory, pending, logs
):
    """The Organiser cannot leave, so they continue with their beneficiary;
    everyone else in the closed cycle chooses (R2-15)."""
    chosen = _lock_with_beneficiaries(session_factory, pending)

    stokvel_id, closed_id, organiser_member_id = _close_cycle(
        session_factory, pending, logs
    )

    with session_factory() as session:
        following = session.scalars(
            select(StokvelCycle).where(
                StokvelCycle.stokvel_id == stokvel_id,
                StokvelCycle.cycle_number == 2,
            )
        ).one()
        assert following.status == "forming"
        assert following.started_at is None
        assert session.get(Stokvel, stokvel_id).current_cycle_id == following.id

        rows = _rows(session, following.id)
        assert set(rows) == {organiser_member_id}
        carried = rows[organiser_member_id]
        assert carried.payout_beneficiary_id == chosen[organiser_member_id]
        assert carried.payout_currency == "ZAR"
        assert carried.payout_position is None
        assert carried.locked is False

        before = _rows(session, closed_id)
        assert before[organiser_member_id].continued is True
        others = [row for key, row in before.items() if key != organiser_member_id]
        assert [row.continued for row in others] == [None]


def test_a_member_who_joined_while_the_cycle_ran_is_in_the_next(
    session_factory, pending, logs
):
    _lock_with_beneficiaries(session_factory, pending)
    stokvel_id, _cycle_id, _organiser = _ids(session_factory, pending)
    joiner = _join_mid_cycle(session_factory, stokvel_id)

    _close_cycle(session_factory, pending, logs)

    with session_factory() as session:
        following = session.scalars(
            select(StokvelCycle).where(
                StokvelCycle.stokvel_id == stokvel_id,
                StokvelCycle.cycle_number == 2,
            )
        ).one()
        row = _rows(session, following.id)[joiner]
        assert row.payout_beneficiary_id is None
        assert row.payout_position is None


def test_a_cycle_that_is_waiting_to_close_opens_nothing(session_factory, pending, logs):
    stokvel_id, _cycle_id, _member_id = _ids(session_factory, pending)
    logs.events = [_event("CycleClosed", START + 2, stokvel_id=stokvel_id)]

    sync_events()

    with session_factory() as session:
        numbers = session.scalars(
            select(StokvelCycle.cycle_number).where(
                StokvelCycle.stokvel_id == stokvel_id
            )
        ).all()
    assert numbers == [1]


def test_replaying_cycle_closed_opens_the_next_cycle_once(
    session_factory, pending, logs
):
    stokvel_id, _cycle_id, _member_id = _close_cycle(session_factory, pending, logs)
    session = session_factory()
    try:
        assert (
            stokvel_sync.apply_event(session, logs.events[0])
            == stokvel_sync.ALREADY_RECORDED
        )
        session.commit()
        numbers = session.scalars(
            select(StokvelCycle.cycle_number).where(
                StokvelCycle.stokvel_id == stokvel_id
            )
        ).all()
    finally:
        session.close()
    assert sorted(numbers) == [1, 2]


def test_a_deactivated_stokvel_gets_no_next_cycle(session_factory, pending, logs):
    stokvel_id, _cycle_id, _member_id = _ids(session_factory, pending)
    with session_factory() as session:
        session.get(Stokvel, stokvel_id).deactivated_at = datetime.now(UTC)
        session.commit()

    _close_cycle(session_factory, pending, logs)

    with session_factory() as session:
        statuses = session.scalars(
            select(StokvelCycle.status).where(StokvelCycle.stokvel_id == stokvel_id)
        ).all()
    assert statuses == ["closed"]


# --- One event never stops the sync ----------------------------------------


def test_an_event_that_fails_is_held_and_the_rest_still_apply(
    session_factory, pending, logs, monkeypatch, caplog
):
    """One event raises; it is held with the error, its changes roll back
    (savepoint), the other event in the range applies, and the cursor moves
    on, so no single event can stop the sync (#346 review)."""
    stokvel_id, cycle_id, member_id = _ids(session_factory, pending)
    _release_every_round(session_factory, pending)
    logs.events = [
        _event("CycleClosed", START + 1, stokvel_id=stokvel_id),
        _contribution_made(stokvel_id, member_id, START + 2),
    ]
    real = stokvel_sync._cycle_closed

    def closes_then_crashes(session, event):
        real(session, event)  # writes, then fails: the savepoint undoes it
        raise RuntimeError("worker hit a bug")

    monkeypatch.setattr(stokvel_sync, "_cycle_closed", closes_then_crashes)

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    with session_factory() as session:
        assert session.get(StokvelCycle, cycle_id).status == "active"
        assert (
            session.get(StokvelContribution, uuid.UUID(pending["id"])).status
            == "confirmed"
        )
    assert _held(session_factory) == [("CycleClosed", "failed", False)]
    assert "RuntimeError: worker hit a bug" in caplog.text
    assert _cursor(session_factory) == logs.head

    monkeypatch.setattr(stokvel_sync, "_cycle_closed", real)  # the bug is fixed
    sync_events()
    with session_factory() as session:
        assert session.get(StokvelCycle, cycle_id).status == "closed"
    assert _held(session_factory) == [("CycleClosed", "failed", True)]


@pytest.mark.parametrize("cursor_exists", [False, True])
def test_a_constraint_failure_while_applying_is_held_not_called_a_race(
    session_factory, pending, logs, caplog, cursor_exists
):
    """A CHECK violation from applying an event is a real fault: it is held
    for a person with the error, not mistaken for another run creating the
    cursor, and nothing it did stays (#346 review)."""
    if cursor_exists:
        sync_events()  # an empty run creates the cursor at the head
        logs.ranges.clear()
    with session_factory() as session:
        # The member can no longer cover the legs: settling breaks
        # accounts_user_balance_nonneg.
        session.get(Account, pending["accounts"]["member"]).account_balance = 0
        session.commit()
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    block = (_cursor(session_factory) or START - 1) + 1
    logs.events = [_contribution_made(stokvel_id, member_id, block)]
    logs.head = block

    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    assert "sync_raced" not in caplog.text
    assert "IntegrityError" in caplog.text
    assert _held(session_factory) == [("ContributionMade", "failed", False)]
    assert _cursor(session_factory) == block
    with session_factory() as session:
        assert (
            session.get(StokvelContribution, uuid.UUID(pending["id"])).status
            == "pending"
        )


def test_a_log_that_will_not_decode_is_held_not_called_an_rpc_error(
    session_factory, pending, logs, caplog
):
    """A drifted ABI copy or a malformed log: held raw with a decode error,
    the rest of the range applies, and once it decodes it is applied."""
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [
        _raw_log(START + 1),
        _contribution_made(stokvel_id, member_id, START + 2),
    ]

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    assert "sync_rpc_error" not in caplog.text
    assert "did not decode" in caplog.text
    assert _held(session_factory) == [(None, "failed", False)]
    assert _cursor(session_factory) == logs.head
    with session_factory() as session:
        assert (
            session.get(StokvelContribution, uuid.UUID(pending["id"])).status
            == "confirmed"
        )

    _release_every_round(session_factory, pending)
    logs.decodes = _event(  # the ABI is fixed
        "CycleClosed",
        START + 1,
        stokvel_id=stokvel_id,
        tx_hash="0x" + "bd" * 32,
    )
    sync_events()
    assert _held(session_factory) == [(None, "failed", True)]


# --- The cursor --------------------------------------------------------------


def test_the_cursor_starts_at_the_start_block_and_reads_in_ranges(
    session_factory, logs
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
    session_factory, logs, monkeypatch
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


def test_a_run_reads_at_most_the_configured_ranges(session_factory, logs, monkeypatch):
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


def test_without_a_start_block_a_first_run_refuses_to_scan_from_genesis(
    session_factory, logs, monkeypatch, caplog
):
    monkeypatch.setenv("STOKVEL_SYNC_START_BLOCK", "")

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_tasks"):
        assert sync_events() == "misconfigured"

    assert logs.ranges == []
    assert "event=stokvel.sync_misconfigured" in caplog.text


def test_with_a_cursor_the_start_block_is_not_needed(
    session_factory, logs, monkeypatch
):
    logs.head = START + 5
    sync_events()
    monkeypatch.setenv("STOKVEL_SYNC_START_BLOCK", "")
    logs.head = START + 8

    assert sync_events() == f"synced to {START + 8}"


def test_an_rpc_error_leaves_the_cursor_for_the_next_run(session_factory, logs, caplog):
    logs.fail = ConnectionError("RPC down")

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_tasks"):
        sync_events()

    assert _cursor(session_factory) is None
    assert "event=stokvel.sync_rpc_error" in caplog.text


def test_a_run_that_finds_the_cursor_moved_stops_and_reports_where_it_is(
    session_factory, pending, logs, caplog
):
    """Two runs overlap: while this one reads the chain, the other moves the
    cursor. This one applies nothing, and reports the cursor where the other
    left it, not where this one started."""
    sync_events()  # creates the cursor at the head
    head = logs.head
    stokvel_id, _cycle_id, member_id = _ids(session_factory, pending)
    logs.events = [_contribution_made(stokvel_id, member_id, head + 1)]
    logs.head = head + 5
    logs.before_return = lambda: _set_cursor(session_factory, head + 3)
    before = _snapshot(session_factory)

    with caplog.at_level(logging.INFO, logger="remitx_worker.stokvel_tasks"):
        assert sync_events() == f"synced to {head + 3}"

    assert _snapshot(session_factory) == before
    assert f"moved the cursor to {head + 3}" in caplog.text


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


def test_without_a_contract_address_nothing_is_read(session_factory, logs, monkeypatch):
    monkeypatch.setenv("STOKVEL_CONTRACT_ADDRESS", "")

    assert sync_events() == "skipped"
    assert logs.ranges == []


# --- Reading and decoding the chain -----------------------------------------


def test_fetch_and_decode_the_three_events_in_chain_order(monkeypatch):
    """Offline: a real web3 contract object decodes hand-built logs."""
    from eth_abi import encode
    from eth_utils import event_abi_to_log_topic

    w3 = Web3()
    asked = []
    stokvel_id, member_id = uuid.uuid4(), uuid.uuid4()
    topics = {
        entry["name"]: event_abi_to_log_topic(entry)
        for entry in stokvel_contract.VAULT_ABI
        if entry["type"] == "event" and entry["name"] in stokvel_contract.SYNCED_EVENTS
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

    fetched = stokvel_contract.fetch_logs(5, 9, w3)
    events = [stokvel_contract.decode_log(entry, w3) for entry in fetched]

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

    not_ours = log(Web3.keccak(text="Paused(address)"), [], b"", 8, 0)
    with pytest.raises(ValueError, match="not a synced vault event"):
        stokvel_contract.decode_log(not_ours, w3)


def test_held_event_arguments_round_trip_through_json():
    args = {"id": b"\x01" * 32, "cycle": 1, "round": 2, "amount": 10**20}
    assert stokvel_sync.args_from_json(stokvel_sync.args_to_json(args)) == args


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
@pytest.mark.parametrize("table", ["cursor", "held"])
def test_no_customer_session_can_see_or_change_the_sync_tables(postgres_app, table):
    """The cursor and the held events are the worker's: a customer route's
    session (bound to a user) reads no row and cannot write one."""
    key = f"0x{uuid.uuid4().hex}"

    def row(suffix=""):
        if table == "cursor":
            return StokvelSyncState(id=key + suffix, last_processed_block=5)
        return StokvelHeldEvent(
            contract_address=key + suffix,
            tx_hash=EVENT_HASH,
            log_index=0,
            block_number=5,
            name="RoundFinalised",
            args={"round": 0},
            reason="waiting",
        )

    model = StokvelSyncState if table == "cursor" else StokvelHeldEvent
    column = (
        StokvelSyncState.id if table == "cursor" else StokvelHeldEvent.contract_address
    )
    token = db.open_session()
    try:
        customer = make_user()
        db.session.add(row())
        db.session.commit()  # unbound, like the worker

        with bound_row_security_context(customer.id, is_admin_route=False):
            assert db.session.scalar(select(model).where(column == key)) is None
            changed = db.session.execute(
                update(model).where(column == key).values(updated_at=datetime.now(UTC))
            )
            assert changed.rowcount == 0
            db.session.add(row("-x"))
            with pytest.raises(DBAPIError, match="row-level security"):
                db.session.flush()
        db.session.rollback()

        assert db.session.scalar(select(model).where(column == key)) is not None
    finally:
        db.close_session(token)
