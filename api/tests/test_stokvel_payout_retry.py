"""Settling a stokvel payout (R3-06, #243): `stokvel.settle_payout` hands its
remittance to the existing chain (`settle_remittance` -> `burn_treasury_tokens`
-> `confirm_treasury_burn`), and `confirm_treasury_burn` finishes the payout
row in the commit that settles or fails the legs.

Same conventions as test_worker_stokvel_settle_payout.py, whose fixtures this
reuses: a scratch SQLite file and a round 0 released through
`record_pool_release`. The chain is test_worker_burn_treasury_tokens.py's
fake, and the broker is a list: every enqueue is captured and `deliver` runs
it, so a test can deliver a message twice, as a redelivery would.

The ticket's "done when", and brief §7.5's settlement test: a retried payout
repeats neither the release, the burn nor the credit.
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import logging
from decimal import Decimal

import pytest
from remitx_api.models.orm.account import Account
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    TYPE_BENEFICIARY_PAYOUT,
    Transaction,
)
from remitx_api.services import queue_service
from remitx_worker import evm_service, reclaim
from remitx_worker.stokvel_payouts import settle_payout
from remitx_worker.tasks import (
    burn_treasury_tokens,
    confirm_treasury_burn,
    settle_remittance,
)
from sqlalchemy import func, select
from tests.test_worker_burn_treasury_tokens import BURN_HASH, FakeChain
from tests.test_worker_stokvel_contribution import (
    _account,
    _user,
    pending,
    session_factory,
)
from tests.test_worker_stokvel_release import (
    ALREADY_RECORDED,
    POOL,
    _record,
    cycle,
)
from tests.test_worker_stokvel_settle_payout import (
    USD_ZAR,
    _payout,
    payee,
    rates,
    released,
)

PAID_OUT = POOL * USD_ZAR  # the beneficiary's ZAR credit


class Broker:
    """The queue, as a list. Every settlement enqueue (and the reclaim
    sweep's `send_task`) lands in `messages`; `deliver` runs them in order
    until none are left, including any they queue."""

    def __init__(self):
        self.messages = []

    def deliver(self, *, twice=False):
        tasks = {
            "settle_remittance": settle_remittance,
            "burn_treasury_tokens": burn_treasury_tokens,
            "confirm_treasury_burn": confirm_treasury_burn,
        }
        outcomes = []
        while self.messages:
            name, args = self.messages.pop(0)
            for _ in range(2 if twice else 1):
                outcomes.append((name, tasks[name](*args)))
        return outcomes


@pytest.fixture
def broker(monkeypatch):
    fake = Broker()
    monkeypatch.setattr(
        queue_service,
        "enqueue_settle_remittance",
        lambda quote_id: fake.messages.append(("settle_remittance", (quote_id,))),
    )
    monkeypatch.setattr(
        queue_service,
        "enqueue_burn_treasury_tokens",
        lambda quote_id: fake.messages.append(("burn_treasury_tokens", (quote_id,))),
    )
    monkeypatch.setattr(
        queue_service,
        "enqueue_confirm_treasury_burn",
        lambda quote_id, tx_hash, error=None: fake.messages.append(
            ("confirm_treasury_burn", (quote_id, tx_hash, error))
        ),
    )

    def send_task(name, args, queue):
        assert name == reclaim.SETTLE_REMITTANCE
        fake.messages.append(("settle_remittance", tuple(args)))

    monkeypatch.setattr(reclaim.celery, "send_task", send_task)
    return fake


@pytest.fixture
def chain(monkeypatch):
    fake = FakeChain()
    monkeypatch.setattr(evm_service, "burn_tokens", fake.burn_tokens)
    monkeypatch.setattr(evm_service, "wait_for_receipt", fake.wait_for_receipt)
    monkeypatch.setattr(evm_service, "transaction_status", fake.transaction_status)
    return fake


def _balances(session_factory, cycle, payee):
    accounts = {
        "treasury": cycle["accounts"]["treasury"],
        "stokvel": cycle["accounts"]["stokvel"],
        "bank": cycle["accounts"]["bank"],
        "token": payee["token"],
        "fiat": payee["fiat"],
        "issuer": payee["issuer"],
    }
    with session_factory() as session:
        return {
            name: session.get(Account, account_id).account_balance
            for name, account_id in accounts.items()
        }


def _settled(before):
    """`before` once the payout is settled: the beneficiary credited in ZAR
    from RemitX's bank, and the pool burnt from the Treasury. The token legs
    out to the beneficiary and back net to nothing."""
    return {
        **before,
        "treasury": before["treasury"] - POOL,
        "issuer": before["issuer"] + POOL,
        "bank": before["bank"] - PAID_OUT,
        "fiat": before["fiat"] + PAID_OUT,
    }


def _leg_statuses(session_factory, quote_id):
    with session_factory() as session:
        return set(
            session.scalars(
                select(Transaction.status).where(Transaction.quote_id == quote_id)
            )
        )


def _counts(session_factory):
    with session_factory() as session:
        return {
            "quotes": session.scalar(select(func.count()).select_from(Quote)),
            "remittances": session.scalar(select(func.count()).select_from(Remittance)),
        }


# --- the hand-off ------------------------------------------------------------


def test_a_created_payout_is_handed_to_settlement(
    session_factory, released, rates, broker
):
    assert settle_payout(str(released)) == "created"

    quote_id = _payout(session_factory, released).quote_id
    assert broker.messages == [("settle_remittance", (str(quote_id),))]


def test_a_payout_that_creates_nothing_hands_nothing_on(
    session_factory, released, rates, broker
):
    settle_payout(str(released))
    broker.messages.clear()

    assert settle_payout(str(released)) == "already_started"

    assert broker.messages == []


def test_a_lost_hand_off_is_logged_and_left_for_the_sweep(
    session_factory, released, rates, broker, monkeypatch, caplog
):
    """The remittance is committed before the enqueue, so a lost message
    leaves it fully pending, which the reclaim sweep queues again."""

    def broker_down(quote_id):
        raise ConnectionError("broker down")

    monkeypatch.setattr(queue_service, "enqueue_settle_remittance", broker_down)

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_payouts"):
        assert settle_payout(str(released)) == "created"

    payout = _payout(session_factory, released)
    assert payout.remittance_status == "processing"
    assert "event=stokvel.payout_hand_off_failed" in caplog.text
    assert str(payout.quote_id) in caplog.text

    assert reclaim.reclaim_pending_settlements(min_age_seconds=0) == 1
    assert broker.messages == [("settle_remittance", (str(payout.quote_id),))]


# --- settling it -------------------------------------------------------------


def test_a_payout_is_burnt_credited_and_finished_once(
    session_factory, cycle, payee, released, rates, broker, chain
):
    before = _balances(session_factory, cycle, payee)

    settle_payout(str(released))
    assert [name for name, _ in broker.deliver()] == [
        "settle_remittance",
        "burn_treasury_tokens",
        "confirm_treasury_burn",
    ]

    assert chain.sent == [BURN_HASH]
    assert chain.burns == [POOL]
    assert _balances(session_factory, cycle, payee) == _settled(before)
    payout = _payout(session_factory, released)
    # Brief §7.2: the burn hash, the beneficiary credit and the remittance
    # reference, together. The credit is the quote's beneficiary_payout leg.
    assert payout.remittance_status == "confirmed"
    assert payout.burn_tx_hash == BURN_HASH
    assert payout.release_status == "released"
    with session_factory() as session:
        remittance = session.get(Remittance, payout.remittance_id)
        assert remittance.quote_id == payout.quote_id
        credit = session.scalar(
            select(Transaction).where(
                Transaction.quote_id == payout.quote_id,
                Transaction.type == TYPE_BENEFICIARY_PAYOUT,
            )
        )
        assert (credit.debit_account_id, credit.amount, credit.status) == (
            payee["fiat"],
            PAID_OUT,
            "confirmed",
        )
    assert _leg_statuses(session_factory, payout.quote_id) == {"confirmed"}


def test_every_message_delivered_twice_still_burns_and_credits_once(
    session_factory, cycle, payee, released, rates, broker, chain
):
    before = _balances(session_factory, cycle, payee)

    settle_payout(str(released))
    settle_payout(str(released))
    broker.deliver(twice=True)

    assert chain.sent == [BURN_HASH]
    assert _balances(session_factory, cycle, payee) == _settled(before)
    assert _payout(session_factory, released).remittance_status == "confirmed"
    assert _counts(session_factory) == {"quotes": 1, "remittances": 1}


def test_retrying_a_settled_payout_repeats_no_release_burn_or_credit(
    session_factory, cycle, payee, released, rates, broker, chain
):
    settle_payout(str(released))
    broker.deliver()
    after = _balances(session_factory, cycle, payee)
    quote_id = str(_payout(session_factory, released).quote_id)

    # Every step again, from the release on
    assert _record(session_factory, cycle) == ALREADY_RECORDED
    assert settle_payout(str(released)) == "already_started"
    assert settle_remittance(quote_id) == "skipped"
    assert burn_treasury_tokens(quote_id) == "skipped"
    assert confirm_treasury_burn(quote_id, BURN_HASH) == "skipped"
    assert reclaim.reclaim_pending_settlements(min_age_seconds=0) == 0
    broker.deliver()

    assert chain.sent == [BURN_HASH]
    assert _balances(session_factory, cycle, payee) == after
    payout = _payout(session_factory, released)
    assert (payout.remittance_status, payout.burn_tx_hash) == ("confirmed", BURN_HASH)
    assert _counts(session_factory) == {"quotes": 1, "remittances": 1}


def test_the_sweep_and_the_hand_off_together_burn_once(
    session_factory, cycle, payee, released, rates, broker, chain
):
    """As found on #243: the reclaim sweep (and the reclaim on worker boot)
    still matches a payout's pending burn, so it can queue the same
    settlement as the hand-off. The chain's own guards keep it to one."""
    before = _balances(session_factory, cycle, payee)

    settle_payout(str(released))
    assert reclaim.reclaim_pending_settlements(min_age_seconds=0) == 1
    assert len(broker.messages) == 2
    broker.deliver()

    assert chain.sent == [BURN_HASH]
    assert _balances(session_factory, cycle, payee) == _settled(before)
    assert _payout(session_factory, released).remittance_status == "confirmed"


# --- a failed burn -----------------------------------------------------------


def _rejected(chain):
    chain.fail_after_signing = evm_service.TransactionRejected(
        BURN_HASH, ValueError("insufficient funds for gas")
    )


def _reverted(chain):
    chain.receipt = evm_service.TransactionReverted(f"burn {BURN_HASH} reverted")


def _never_signed(chain):
    chain.fail_before_signing = ConnectionError("rpc down")


@pytest.mark.parametrize("fail_it", [_rejected, _reverted, _never_signed])
def test_a_failed_burn_fails_the_payout_and_keeps_the_release(
    session_factory, cycle, payee, released, rates, broker, chain, caplog, fail_it
):
    """No tokens were burnt, so no balance moves, and the payout is left
    `failed` for a person. The release is a separate status and stays."""
    before = _balances(session_factory, cycle, payee)
    fail_it(chain)

    settle_payout(str(released))
    with caplog.at_level(logging.ERROR, logger="remitx_worker.tasks"):
        broker.deliver()

    payout = _payout(session_factory, released)
    assert payout.remittance_status == "failed"
    assert payout.release_status == "released"
    # A hash on a failed burn is no proof of one (doc section 3)
    assert payout.burn_tx_hash is None
    assert _leg_statuses(session_factory, payout.quote_id) == {"failed"}
    assert _balances(session_factory, cycle, payee) == before
    assert "event=stokvel.payout_settlement_failed" in caplog.text
    assert str(payout.id) in caplog.text


def test_retrying_a_failed_payout_creates_and_burns_nothing(
    session_factory, cycle, payee, released, rates, broker, chain
):
    _reverted(chain)
    settle_payout(str(released))
    broker.deliver()
    after = _balances(session_factory, cycle, payee)
    quote_id = str(_payout(session_factory, released).quote_id)

    assert _record(session_factory, cycle) == ALREADY_RECORDED
    assert settle_payout(str(released)) == "already_started"
    assert settle_remittance(quote_id) == "skipped"
    assert burn_treasury_tokens(quote_id) == "skipped"
    assert confirm_treasury_burn(quote_id, BURN_HASH) == "skipped"
    assert reclaim.reclaim_pending_settlements(min_age_seconds=0) == 0
    broker.deliver()

    assert len(chain.sent) == 1
    assert _balances(session_factory, cycle, payee) == after
    assert _payout(session_factory, released).remittance_status == "failed"
    assert _counts(session_factory) == {"quotes": 1, "remittances": 1}


def test_a_burn_left_unconfirmed_leaves_the_payout_processing(
    session_factory, cycle, payee, released, rates, broker, chain, monkeypatch
):
    """No receipt after the retries: the burn may still land, so neither the
    legs nor the payout are finished; a person looks."""
    before = _balances(session_factory, cycle, payee)
    chain.receipt = TimeoutError("no receipt")
    monkeypatch.setattr(burn_treasury_tokens, "max_retries", 0)

    settle_payout(str(released))
    outcomes = broker.deliver()

    assert ("burn_treasury_tokens", "awaiting_receipt") in outcomes
    payout = _payout(session_factory, released)
    assert (payout.remittance_status, payout.burn_tx_hash) == ("processing", None)
    assert _balances(session_factory, cycle, payee) == before
