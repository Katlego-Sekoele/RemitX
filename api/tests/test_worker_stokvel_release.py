"""The pool release (R3-04, #241): `stokvel_ledger.record_pool_release`, the guard
every release is recorded through, and `stokvel.release_pool`, which sends
`finalise` for a round that became due with time.

Same conventions as test_worker_stokvel_contribution.py, whose fixtures this
reuses: the task runs against a scratch SQLite file with the chain faked
(`stokvel_contract.finalise` and `round_finalised`, and
`evm_service.wait_for_receipt`). The event sync's side of a release is in
test_stokvel_sync_events.py.

The ticket's "done when": a finalised round credits the books exactly once,
however many times and from wherever it is recorded.
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import logging
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from remitx_api.models.orm.account import CURRENCY_TOKEN, Account
from remitx_api.models.orm.stokvel_contribution import StokvelContribution
from remitx_api.models.orm.stokvel_cycle import StokvelCycle
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    TYPE_STOKVEL_POOL_RELEASE,
    Transaction,
)
from remitx_api.services import queue_service
from remitx_worker import evm_service, stokvel_contract, stokvel_ledger, stokvel_release
from remitx_worker.celery_app import celery
from remitx_worker.stokvel_contract import ContractEvent
from remitx_worker.stokvel_ledger import (
    ALREADY_RECORDED,
    RECORDED,
    ReleaseConflict,
    ensure_payout,
    record_pool_release,
)
from remitx_worker.stokvel_release import release_pool
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tests.test_worker_stokvel_contribution import (
    BLOCK,
    CONTRIBUTION,
    W3,
    pending,
    session_factory,
)
from web3 import Web3
from web3.exceptions import TimeExhausted

RELEASE_HASH = "0x" + "f1" * 32
OTHER_HASH = "0x" + "f2" * 32
POOL = 2 * CONTRIBUTION  # two members


@pytest.fixture
def cycle(session_factory, pending):
    """The pending contribution's cycle, its stokvel, and who each round pays."""
    with session_factory() as session:
        cycle_id = session.get(StokvelContribution, uuid.UUID(pending["id"])).cycle_id
        stokvel_id = session.get(StokvelCycle, cycle_id).stokvel_id
        members = {
            row.payout_position: row.member_id
            for row in session.scalars(
                select(StokvelCycleMember).where(
                    StokvelCycleMember.cycle_id == cycle_id
                )
            )
        }
    return {
        "id": cycle_id,
        "stokvel_id": stokvel_id,
        "members": members,
        "accounts": pending["accounts"],
    }


def _event(cycle, round_=0, *, tx_hash=RELEASE_HASH, pool=POOL, member=None):
    return ContractEvent(
        name="RoundFinalised",
        args={
            "id": evm_service.uuid_to_bytes32(cycle["stokvel_id"]),
            "cycle": 1,
            "round": round_,
            "memberId": evm_service.uuid_to_bytes32(
                cycle["members"][round_] if member is None else member
            ),
            "pool": evm_service.to_base_units(pool),
        },
        tx_hash=tx_hash,
        block_number=BLOCK,
        log_index=0,
    )


class FakeFinalise:
    """`stokvel_contract.finalise` / `round_finalised` and
    `evm_service.wait_for_receipt`, without a chain. Like the real `finalise`,
    the hash goes to `on_signed` before the "send". `before_signing` and
    `after_signing` are exceptions raised by successive calls; `after_send`
    runs once the transaction is out (another worker acting meanwhile);
    `receipt` an exception every wait raises."""

    def __init__(self, cycle):
        self.cycle = cycle
        self.finalised = []
        self.sent = []
        self.waits = []
        self.before_signing: list[BaseException] = []
        self.after_signing: list[BaseException] = []
        self.after_send = None
        self.receipt = None
        self.events = None

    def finalise(self, stokvel_id, round_, *, on_signed=None, w3=None):
        assert w3 is W3
        self.finalised.append((stokvel_id, round_))
        if self.before_signing:
            raise self.before_signing.pop(0)
        if on_signed is not None:
            on_signed(RELEASE_HASH)
        if self.after_signing:
            raise self.after_signing.pop(0)
        self.sent.append(RELEASE_HASH)
        if self.after_send is not None:
            self.after_send()
        return RELEASE_HASH

    def wait_for_receipt(self, tx_hash, timeout=120, w3=None):
        self.waits.append(tx_hash)
        if isinstance(self.receipt, BaseException):
            raise self.receipt
        return {"transactionHash": tx_hash, "status": 1, "blockNumber": BLOCK}

    def round_finalised(self, receipt, w3):
        assert w3 is W3
        if self.events is not None:
            return self.events
        return [_event(self.cycle, 0, tx_hash=receipt["transactionHash"])]


@pytest.fixture
def chain(monkeypatch, cycle):
    fake = FakeFinalise(cycle)
    monkeypatch.setattr(stokvel_contract, "finalise", fake.finalise)
    monkeypatch.setattr(stokvel_contract, "round_finalised", fake.round_finalised)
    monkeypatch.setattr(evm_service, "wait_for_receipt", fake.wait_for_receipt)
    return fake


def _fund(session_factory, cycle, amount=POOL):
    """Book `amount` into the stokvel, as its confirmed contributions would
    have: a release takes the whole pool out of `STOKVEL`, which can never go
    below zero."""
    accounts = cycle["accounts"]
    with session_factory() as session:
        for name, change in (("treasury", -amount), ("stokvel", amount)):
            session.execute(
                update(Account)
                .where(Account.account_id == accounts[name])
                .values(account_balance=Account.account_balance + change)
            )
        session.commit()


def _balances(session_factory, cycle):
    with session_factory() as session:
        return {
            name: session.get(Account, cycle["accounts"][name]).account_balance
            for name in ("stokvel", "treasury")
        }


def _payouts(session_factory):
    """(round, status, hash, block) for every payout, by round."""
    with session_factory() as session:
        return [
            (p.round, p.release_status, p.release_tx_hash, p.release_block_number)
            for p in session.scalars(
                select(StokvelPayout).order_by(StokvelPayout.round)
            )
        ]


def _release_legs(session_factory):
    with session_factory() as session:
        return session.scalars(
            select(Transaction).where(Transaction.type == TYPE_STOKVEL_POOL_RELEASE)
        ).all()


def _record(session_factory, cycle, round_=0, *, tx_hash=RELEASE_HASH, **kwargs):
    """`record_pool_release` as the event sync calls it, in its own commit."""
    args = {"pool": POOL, "member_id": cycle["members"][round_], **kwargs}
    with session_factory() as session:
        outcome = record_pool_release(
            session,
            cycle_id=cycle["id"],
            round_=round_,
            tx_hash=tx_hash,
            block_number=BLOCK,
            **args,
        )
        session.commit()
    return outcome


# --- record_pool_release -----------------------------------------------------


def test_a_release_moves_the_pool_from_the_stokvel_to_the_treasury_once(
    session_factory, cycle
):
    _fund(session_factory, cycle)
    before = _balances(session_factory, cycle)

    assert _record(session_factory, cycle) == RECORDED

    assert _payouts(session_factory) == [(0, "released", RELEASE_HASH, BLOCK)]
    [leg] = _release_legs(session_factory)
    assert (leg.amount, leg.currency, leg.status) == (
        POOL,
        CURRENCY_TOKEN,
        STATUS_CONFIRMED,
    )
    assert (leg.credit_account_id, leg.debit_account_id) == (
        cycle["accounts"]["stokvel"],
        cycle["accounts"]["treasury"],
    )
    assert _balances(session_factory, cycle) == {
        "stokvel": before["stokvel"] - POOL,
        "treasury": before["treasury"] + POOL,
    }
    with session_factory() as session:
        payout = session.scalars(select(StokvelPayout)).one()
        assert payout.release_tx_id == leg.tx_id
        assert payout.member_id == cycle["members"][0]
        assert payout.released_at is not None
        assert payout.remittance_status == "pending"  # R3-05 pays it out


def test_recording_it_again_books_nothing(session_factory, cycle):
    """The ticket's "done when": the event sync and `release_pool` can both
    see the same release; only the first books it."""
    _fund(session_factory, cycle)
    _record(session_factory, cycle)
    after_first = _balances(session_factory, cycle)

    assert _record(session_factory, cycle) == ALREADY_RECORDED
    assert _record(session_factory, cycle, tx_hash=RELEASE_HASH.upper()) == (
        ALREADY_RECORDED
    )

    assert len(_release_legs(session_factory)) == 1
    assert _balances(session_factory, cycle) == after_first


def test_a_release_recorded_meanwhile_by_another_worker_is_not_booked_twice(
    session_factory, cycle
):
    """The race: this worker read the payout as pending, and another recorded
    it before this one's guarded update. The update matches nothing, and the
    leg this worker wrote is rolled back with its savepoint."""
    _fund(session_factory, cycle, 2 * POOL)
    _record(session_factory, cycle)
    after_first = _balances(session_factory, cycle)
    real_ensure = stokvel_ledger.ensure_payout

    def stale_read(session, cycle_id, round_):
        payout = real_ensure(session, cycle_id, round_)
        session.expunge(payout)
        payout.release_status = "pending"  # what this worker last saw
        return payout

    with patch.object(stokvel_ledger, "ensure_payout", stale_read):
        assert _record(session_factory, cycle) == ALREADY_RECORDED

    assert len(_release_legs(session_factory)) == 1
    assert _balances(session_factory, cycle) == after_first


def test_a_payout_another_worker_created_first_is_used_not_duplicated(
    session_factory, cycle
):
    """Both workers found no payout row and both inserted one. The second
    insert hits uq_stokvel_payouts_cycle_id_round and uses the first's row."""
    with session_factory() as session:
        ensure_payout(session, cycle["id"], 0)
        session.commit()
    real_payout = stokvel_ledger._payout
    calls = []

    def missed_once(session, cycle_id, round_):
        calls.append(round_)
        return None if len(calls) == 1 else real_payout(session, cycle_id, round_)

    with (
        session_factory() as session,
        patch.object(stokvel_ledger, "_payout", missed_once),
    ):
        assert ensure_payout(session, cycle["id"], 0).round == 0
        session.commit()

    assert _payouts(session_factory) == [(0, "pending", None, None)]


def test_a_release_for_another_member_or_hash_is_refused_and_writes_nothing(
    session_factory, cycle
):
    _fund(session_factory, cycle, 2 * POOL)
    with pytest.raises(ReleaseConflict):
        _record(session_factory, cycle, member_id=cycle["members"][1])
    assert _payouts(session_factory) == []

    _record(session_factory, cycle)
    with pytest.raises(ReleaseConflict):
        _record(session_factory, cycle, tx_hash=OTHER_HASH)

    assert _payouts(session_factory) == [(0, "released", RELEASE_HASH, BLOCK)]
    assert len(_release_legs(session_factory)) == 1


def test_a_round_that_pays_nobody_is_refused(session_factory, cycle):
    with pytest.raises(ReleaseConflict), session_factory() as session:
        ensure_payout(session, cycle["id"], 5)


def test_a_release_the_stokvel_cannot_cover_changes_nothing(session_factory, cycle):
    """A contribution in the pool is not recorded yet. `STOKVEL` cannot go
    below zero, so recording fails and leaves the books as they were; the
    caller records it again later."""
    before = _balances(session_factory, cycle)

    with pytest.raises(IntegrityError), session_factory() as session:
        record_pool_release(
            session,
            cycle_id=cycle["id"],
            round_=0,
            member_id=cycle["members"][0],
            pool=POOL,
            tx_hash=RELEASE_HASH,
            block_number=BLOCK,
        )

    assert _balances(session_factory, cycle) == before
    assert _release_legs(session_factory) == []


def test_a_pool_that_differs_from_the_contributions_is_booked_as_the_chain_says(
    session_factory, cycle, caplog
):
    _fund(session_factory, cycle)
    pool = POOL - Decimal("1")

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_ledger"):
        _record(session_factory, cycle, pool=pool)

    assert "event=stokvel.release_amount_differs" in caplog.text
    [leg] = _release_legs(session_factory)
    assert leg.amount == pool


# --- release_pool ------------------------------------------------------------


def test_a_due_round_is_finalised_and_recorded(session_factory, cycle, chain):
    _fund(session_factory, cycle)

    assert release_pool(str(cycle["id"]), 0) == "released"

    assert chain.finalised == [(cycle["stokvel_id"], 0)]
    assert chain.waits == [RELEASE_HASH]
    assert _payouts(session_factory) == [(0, "released", RELEASE_HASH, BLOCK)]
    assert len(_release_legs(session_factory)) == 1


def test_a_released_round_is_never_finalised_again(session_factory, cycle, chain):
    _fund(session_factory, cycle)
    release_pool(str(cycle["id"]), 0)
    after_first = _balances(session_factory, cycle)

    assert release_pool(str(cycle["id"]), 0) == "already_released"

    assert len(chain.finalised) == 1
    assert len(_release_legs(session_factory)) == 1
    assert _balances(session_factory, cycle) == after_first


def test_a_redelivery_waits_on_the_stored_hash_and_never_sends_twice(
    session_factory, cycle, chain
):
    """The first delivery stored its hash and sent, then stopped before the
    receipt. The redelivery finds the payout claimed and waits on that hash."""
    _fund(session_factory, cycle)
    chain.receipt = TimeExhausted("not mined in 120s")
    with pytest.raises(TimeExhausted):
        release_pool(str(cycle["id"]), 0)  # direct call: the retry re-raises
    assert _payouts(session_factory) == [(0, "processing", RELEASE_HASH, None)]

    chain.receipt = None
    assert release_pool(str(cycle["id"]), 0) == "released"

    assert len(chain.finalised) == 1
    assert chain.waits == [RELEASE_HASH, RELEASE_HASH]
    assert _payouts(session_factory) == [(0, "released", RELEASE_HASH, BLOCK)]


def test_already_finalised_hands_the_claim_back_for_the_sync(
    session_factory, cycle, chain
):
    """A `contribute` released the round first: nothing is sent, and the event
    sync records that release from its `RoundFinalised`."""
    chain.before_signing = [
        stokvel_contract.ContractRefused("AlreadyFinalised", "reverted")
    ]

    assert release_pool(str(cycle["id"]), 0) == "already_released"

    assert chain.sent == []
    assert _payouts(session_factory) == [(0, "pending", None, None)]
    assert _release_legs(session_factory) == []


def test_a_round_not_yet_due_is_left_pending(session_factory, cycle, chain):
    chain.before_signing = [
        stokvel_contract.ContractRefused("NotYetFinalisable", "reverted")
    ]

    assert release_pool(str(cycle["id"]), 0) == "not_due"

    assert chain.sent == []
    assert _payouts(session_factory) == [(0, "pending", None, None)]


def test_a_paused_contract_is_retried_then_released(session_factory, cycle, chain):
    _fund(session_factory, cycle)
    chain.before_signing = [stokvel_contract.ContractRefused("EnforcedPause", "x")]

    assert release_pool.apply(args=[str(cycle["id"]), 0]).get() == "released"

    assert len(chain.finalised) == 2
    assert chain.sent == [RELEASE_HASH]


def test_a_refusal_that_will_not_pass_sends_nothing_and_stays_pending(
    session_factory, cycle, chain, caplog
):
    chain.before_signing = [stokvel_contract.ContractRefused("CycleNotOpen", "x")]

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_release"):
        assert release_pool(str(cycle["id"]), 0) == "refused"

    assert "event=stokvel.release_refused" in caplog.text
    assert _payouts(session_factory) == [(0, "pending", None, None)]


def test_a_refused_send_drops_its_hash_and_retries(session_factory, cycle, chain):
    _fund(session_factory, cycle)
    chain.after_signing = [
        evm_service.TransactionRejected(RELEASE_HASH, Exception("insufficient funds"))
    ]

    assert release_pool.apply(args=[str(cycle["id"]), 0]).get() == "released"

    assert len(chain.finalised) == 2
    assert chain.sent == [RELEASE_HASH]


def test_a_reverted_finalise_never_undoes_the_release_the_sync_recorded(
    session_factory, cycle, chain
):
    """Our `finalise` went out, then a `contribute` released the round and the
    sync recorded it with its own hash, so ours reverted. The hand-back only
    matches our hash, so the recorded release stands."""
    _fund(session_factory, cycle)
    chain.after_send = lambda: _record(session_factory, cycle, tx_hash=OTHER_HASH)
    chain.receipt = evm_service.TransactionReverted("reverted")

    assert release_pool(str(cycle["id"]), 0) == "reverted"

    assert _payouts(session_factory) == [(0, "released", OTHER_HASH, BLOCK)]
    assert len(_release_legs(session_factory)) == 1


def test_a_reverted_finalise_with_no_release_hands_the_claim_back(
    session_factory, cycle, chain
):
    chain.receipt = evm_service.TransactionReverted("reverted")

    assert release_pool(str(cycle["id"]), 0) == "reverted"

    assert _payouts(session_factory) == [(0, "pending", None, None)]


def test_a_mined_release_it_cannot_record_is_left_for_the_sync(
    session_factory, cycle, chain, caplog
):
    """Mined, but a contribution in the pool is not recorded yet. The payout
    stays `processing` with its hash; the sync records it from the event."""
    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_release"):
        assert release_pool(str(cycle["id"]), 0) == "mined_unrecorded"

    assert "event=stokvel.release_left_for_sync" in caplog.text
    assert _payouts(session_factory) == [(0, "processing", RELEASE_HASH, None)]

    _fund(session_factory, cycle)
    assert _record(session_factory, cycle) == RECORDED
    assert _payouts(session_factory) == [(0, "released", RELEASE_HASH, BLOCK)]


def test_a_receipt_without_the_rounds_release_is_left_for_a_person(
    session_factory, cycle, chain, caplog
):
    chain.events = []

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_release"):
        assert release_pool(str(cycle["id"]), 0) == "mined_unrecorded"

    assert "event=stokvel.release_event_missing" in caplog.text
    assert _payouts(session_factory) == [(0, "processing", RELEASE_HASH, None)]


def test_no_receipt_retries_the_same_hash_then_leaves_it_for_a_person(
    session_factory, cycle, chain, caplog
):
    chain.receipt = TimeExhausted("not mined in 120s")

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_release"):
        result = release_pool.apply(args=[str(cycle["id"]), 0]).get()

    assert result == "awaiting_receipt"
    assert len(chain.finalised) == 1
    assert chain.waits == [RELEASE_HASH] * (stokvel_release.MAX_RETRIES + 1)
    assert "event=stokvel.release_unconfirmed" in caplog.text
    assert _payouts(session_factory) == [(0, "processing", RELEASE_HASH, None)]


def test_unknown_cycles_and_unscheduled_rounds_are_skipped(
    session_factory, cycle, chain
):
    assert release_pool("not-a-uuid", 0) == "skipped"
    assert release_pool(str(uuid.uuid4()), 0) == "skipped"
    assert release_pool(str(cycle["id"]), 5) == "skipped"
    assert chain.finalised == []
    assert _payouts(session_factory) == []


# --- Wiring and the contract wrapper -----------------------------------------


def test_the_api_and_the_worker_agree_on_the_task_name():
    assert queue_service.RELEASE_POOL == release_pool.name
    assert release_pool.name in celery.tasks


def test_finalise_sends_the_packed_stokvel_id_and_round(monkeypatch):
    sent, encoded = [], []
    vault = type(
        "Vault",
        (),
        {
            "address": "0xVault",
            "encode_abi": lambda self, name, args: (
                encoded.append((name, args)) or f"data:{name}"
            ),
        },
    )()

    def submit(tx, w3=None, *, on_signed=None):
        sent.append(tx)
        on_signed(RELEASE_HASH)
        return RELEASE_HASH

    monkeypatch.setattr(stokvel_contract, "vault", lambda w3: vault)
    monkeypatch.setattr(evm_service, "submit_transaction", submit)
    stokvel_id, signed = uuid.uuid4(), []

    assert (
        stokvel_contract.finalise(stokvel_id, 3, on_signed=signed.append, w3=W3)
        == RELEASE_HASH
    )
    assert encoded == [("finalise", [stokvel_id.bytes + bytes(16), 3])]
    assert sent == [{"to": "0xVault", "data": "data:finalise"}]
    assert signed == [RELEASE_HASH]


def test_round_finalised_reads_the_vaults_releases_from_a_receipt(monkeypatch):
    """Offline: a real web3 contract object decodes hand-built receipt logs,
    keeping only the vault's `RoundFinalised` (a `contribute`'s receipt also
    has its `ContributionMade` and the token's `Transfer`)."""
    from eth_abi import encode
    from eth_utils import event_abi_to_log_topic
    from hexbytes import HexBytes

    vault_address = "0x2f240705314BB79780522635eA47d20072CB8Fe1"
    w3 = Web3()
    monkeypatch.setattr(
        stokvel_contract,
        "vault",
        lambda w3_: w3_.eth.contract(
            address=vault_address, abi=stokvel_contract.VAULT_ABI
        ),
    )
    topics = {
        entry["name"]: event_abi_to_log_topic(entry)
        for entry in stokvel_contract.VAULT_ABI
        if entry["type"] == "event"
    }
    stokvel_id, member_id = uuid.uuid4(), uuid.uuid4()
    sid = evm_service.uuid_to_bytes32(stokvel_id)
    mid = evm_service.uuid_to_bytes32(member_id)

    def log(address, topic, extra, data, index):
        return {
            "address": address,
            "topics": [HexBytes(topic), *[HexBytes(t) for t in extra]],
            "data": HexBytes(data),
            "blockNumber": BLOCK,
            "transactionHash": HexBytes(bytes.fromhex(RELEASE_HASH[2:])),
            "logIndex": index,
            "blockHash": HexBytes(b"\x00" * 32),
            "transactionIndex": 0,
            "removed": False,
        }

    released = encode(["uint32", "uint8", "uint256"], [1, 0, 2 * 10**20])
    receipt = {
        "logs": [
            log(
                vault_address,
                topics["ContributionMade"],
                [sid, mid],
                encode(["uint32", "uint8", "uint256"], [1, 1, 10**20]),
                0,
            ),
            log(vault_address, topics["RoundFinalised"], [sid, mid], released, 1),
            log(
                "0x" + "11" * 20,
                Web3.keccak(text="Transfer(address,address,uint256)"),
                [],
                b"",
                2,
            ),
        ]
    }

    [event] = stokvel_contract.round_finalised(receipt, w3)

    assert event.name == "RoundFinalised"
    assert (event.args["round"], event.args["pool"]) == (0, 2 * 10**20)
    assert evm_service.bytes32_to_uuid(event.args["memberId"]) == member_id
    assert (event.tx_hash, event.block_number) == (RELEASE_HASH, BLOCK)
