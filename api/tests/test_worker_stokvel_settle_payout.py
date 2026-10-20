"""The payout of a released pool (R3-05, #242): `stokvel.settle_payout`,
`quote_service.price_stokvel_payout` and `queue_released_payouts`.

Same conventions as test_worker_stokvel_release.py, whose fixtures this
reuses: a scratch SQLite file, a round 0 released through
`record_pool_release`, and rates from a fake provider instead of the live
API.

The ticket's "done when": a released round produces one quote and one
remittance, paid to the recipient's beneficiary.
"""

# The shared fixtures are imported by name, which pytest needs and ruff
# reads as unused or redefined.
# ruff: noqa: F401, F811

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.config import Config
from remitx_api.db.request_db_session import (
    reset_request_db_session,
    set_request_db_session,
)
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    TYPE_EXTERNAL,
    TYPE_PLATFORM_FIAT,
    TYPE_USER,
    Account,
)
from remitx_api.models.orm.beneficiary import Beneficiary
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.stokvel_cycle_member import StokvelCycleMember
from remitx_api.models.orm.stokvel_member import StokvelMember
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.transaction import (
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_REMITTANCE,
    TYPE_TOKEN_BURN,
    Transaction,
)
from remitx_api.services import queue_service, quote_service
from remitx_api.services.exchange_rate_provider import (
    RateFetchError,
    use_rate_provider,
)
from remitx_worker import stokvel_payouts
from remitx_worker.stokvel_ledger import ensure_payout
from remitx_worker.stokvel_payouts import queue_released_payouts, settle_payout
from sqlalchemy import delete, func, select, update
from tests.test_worker_stokvel_contribution import (
    _account,
    _user,
    pending,
    session_factory,
)
from tests.test_worker_stokvel_release import POOL, _fund, _record, cycle

USD_ZAR = Decimal("18.5")
ZAR_NAD = Decimal("0.95")


class FakeRates:
    """The live rate API, without the network. `fail` makes every fetch
    fail, as an outage does."""

    def __init__(self):
        self.fail = False
        self.rates = {
            (CURRENCY_USD, CURRENCY_ZAR): USD_ZAR,
            (CURRENCY_USD, CURRENCY_NAD): USD_ZAR,
            (CURRENCY_USD, CURRENCY_USD): Decimal("1"),
            (CURRENCY_ZAR, CURRENCY_ZAR): Decimal("1"),
            (CURRENCY_ZAR, CURRENCY_NAD): ZAR_NAD,
        }

    def get_rate(self, base_currency, quote_currency):
        if self.fail:
            raise RateFetchError("rate API down")
        return self.rates[(base_currency, quote_currency)]


@pytest.fixture
def rates():
    fake = FakeRates()
    use_rate_provider(fake)
    yield fake
    use_rate_provider(None)


@pytest.fixture
def payee(session_factory, cycle):
    """Round 0's member has chosen a beneficiary, paid in ZAR, who has the
    token and ZAR accounts a payout credits. The token issuer the burn leg
    pays is seeded too."""
    with session_factory() as session:
        recipient = _user(session)
        token_account = _account(
            session, type_=TYPE_USER, currency=CURRENCY_TOKEN, user_id=recipient
        )
        fiat_account = _account(
            session, type_=TYPE_USER, currency=CURRENCY_ZAR, user_id=recipient
        )
        member_user = session.scalar(
            select(StokvelMember.user_id).where(StokvelMember.id == cycle["members"][0])
        )
        beneficiary = Beneficiary(
            sender_user_id=member_user,
            linked_user_id=recipient,
            payout_currency=CURRENCY_ZAR,
            relationship="partner",
        )
        session.add(beneficiary)
        session.flush()
        session.execute(
            update(StokvelCycleMember)
            .where(
                StokvelCycleMember.cycle_id == cycle["id"],
                StokvelCycleMember.member_id == cycle["members"][0],
            )
            .values(
                payout_beneficiary_id=beneficiary.beneficiary_id,
                payout_currency=CURRENCY_ZAR,
            )
        )
        issuer = Account(
            account_id=uuid.uuid4(),
            type=TYPE_EXTERNAL,
            account_currency=CURRENCY_TOKEN,
            account_balance=Decimal("0"),
            label=Config().UCTUSD_ISSUER_LABEL,
        )
        session.add(issuer)
        session.commit()
        return {
            "user": recipient,
            "beneficiary": beneficiary.beneficiary_id,
            "token": token_account,
            "fiat": fiat_account,
            "issuer": issuer.account_id,
        }


@pytest.fixture
def released(session_factory, cycle, payee):
    """Round 0's pool released and recorded: the payout R3-05 pays out."""
    _fund(session_factory, cycle)
    _record(session_factory, cycle)
    with session_factory() as session:
        return session.scalar(select(StokvelPayout.id).where(StokvelPayout.round == 0))


@pytest.fixture
def queued(monkeypatch):
    calls = []
    monkeypatch.setattr(
        queue_service,
        "enqueue_settle_payout",
        lambda payout_id: calls.append(payout_id),
    )
    return calls


def _payout(session_factory, payout_id):
    with session_factory() as session:
        row = session.get(StokvelPayout, payout_id)
        session.expunge(row)
        return row


def _counts(session_factory):
    with session_factory() as session:
        return {
            "quotes": session.scalar(select(func.count()).select_from(Quote)),
            "remittances": session.scalar(select(func.count()).select_from(Remittance)),
        }


def _balances(session_factory):
    with session_factory() as session:
        return sorted(
            (str(a.account_id), a.account_balance)
            for a in session.scalars(select(Account))
        )


# --- settle_payout -----------------------------------------------------------


def test_a_released_round_becomes_one_quote_and_one_remittance(
    session_factory, cycle, payee, released, rates
):
    before = _balances(session_factory)

    assert settle_payout(str(released)) == "created"

    payout = _payout(session_factory, released)
    assert payout.remittance_status == "processing"
    with session_factory() as session:
        quote = session.get(Quote, payout.quote_id)
        # The stokvel sends, in its own currency; the full pool, no fee
        assert (quote.stokvel_id, quote.sender_user_id) == (cycle["stokvel_id"], None)
        assert quote.beneficiary_user_id == payee["user"]
        assert quote.status == "USED"
        assert (quote.sender_transaction_fee, quote.exchange_rate_margin) == (0, 0)
        assert quote.token_amount == POOL
        assert (quote.sender_currency, quote.sender_amount) == (
            CURRENCY_ZAR,
            POOL * USD_ZAR,
        )
        assert (quote.receiver_currency, quote.receiver_amount) == (
            CURRENCY_ZAR,
            POOL * USD_ZAR,
        )
        legs = session.scalars(
            select(Transaction).where(Transaction.quote_id == quote.quote_id)
        ).all()
        treasury = cycle["accounts"]["treasury"]
        bank = cycle["accounts"]["bank"]
        # Paid from the Treasury, where the release put the pool: not back
        # through STOKVEL (#241)
        assert sorted(
            (leg.type, leg.credit_account_id, leg.debit_account_id, leg.amount)
            for leg in legs
        ) == sorted(
            [
                (TYPE_REMITTANCE, treasury, payee["token"], POOL),
                (TYPE_REMITTANCE, payee["token"], treasury, POOL),
                (TYPE_TOKEN_BURN, treasury, payee["issuer"], POOL),
                (TYPE_BENEFICIARY_PAYOUT, bank, payee["fiat"], POOL * USD_ZAR),
            ]
        )
        assert {leg.status for leg in legs} == {"pending"}
        remittance = session.get(Remittance, payout.remittance_id)
        paid_out = session.get(Transaction, remittance.tx_id)
        assert (paid_out.credit_account_id, paid_out.debit_account_id) == (
            treasury,
            payee["token"],
        )
    # Pending legs move nothing; settlement (R3-06) does
    assert _balances(session_factory) == before


def test_settling_it_again_creates_nothing(session_factory, released, rates):
    settle_payout(str(released))

    assert settle_payout(str(released)) == "already_started"

    assert _counts(session_factory) == {"quotes": 1, "remittances": 1}


def test_two_deliveries_at_once_create_one_remittance(
    session_factory, released, rates, monkeypatch
):
    """Both read the payout as not started; the second's guarded update
    matches nothing, and its quote, legs and remittance roll back."""
    real_price = stokvel_payouts._price
    raced = []

    def other_delivery_first(*args):
        if not raced:
            raced.append(True)
            assert settle_payout(str(released)) == "created"
        return real_price(*args)

    monkeypatch.setattr(stokvel_payouts, "_price", other_delivery_first)

    assert settle_payout(str(released)) == "already_started"

    assert _counts(session_factory) == {"quotes": 1, "remittances": 1}
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Transaction)
                .where(Transaction.quote_id.is_not(None))
            )
            == 4
        )


def test_a_round_not_released_is_not_paid_out(session_factory, cycle, payee, rates):
    with session_factory() as session:
        payout_id = ensure_payout(session, cycle["id"], 0).id
        session.commit()

    assert settle_payout(str(payout_id)) == "not_released"
    assert _counts(session_factory) == {"quotes": 0, "remittances": 0}


def _no_beneficiary(session, cycle, payee):
    session.execute(
        update(StokvelCycleMember)
        .where(StokvelCycleMember.member_id == cycle["members"][0])
        .values(payout_beneficiary_id=None, payout_currency=None)
    )


def _beneficiary_now_paid_in_nad(session, cycle, payee):
    session.execute(
        update(Beneficiary)
        .where(Beneficiary.beneficiary_id == payee["beneficiary"])
        .values(payout_currency=CURRENCY_NAD)
    )


def _no_account_to_credit(session, cycle, payee):
    session.execute(delete(Account).where(Account.account_id == payee["fiat"]))


@pytest.mark.parametrize(
    "break_it", [_no_beneficiary, _beneficiary_now_paid_in_nad, _no_account_to_credit]
)
def test_a_beneficiary_that_no_longer_fits_is_failed_for_a_person(
    session_factory, cycle, payee, released, rates, caplog, break_it
):
    with session_factory() as session:
        break_it(session, cycle, payee)
        session.commit()

    with caplog.at_level(logging.ERROR, logger="remitx_worker.stokvel_payouts"):
        assert settle_payout(str(released)) == "failed"

    assert "event=stokvel.payout_needs_a_person" in caplog.text
    payout = _payout(session_factory, released)
    assert (payout.remittance_status, payout.quote_id) == ("failed", None)
    assert _counts(session_factory) == {"quotes": 0, "remittances": 0}


def test_a_rate_it_cannot_get_leaves_the_payout_pending(
    session_factory, released, rates, caplog
):
    rates.fail = True  # and no rate stored yet to fall back on

    with caplog.at_level(logging.WARNING, logger="remitx_worker.stokvel_payouts"):
        assert settle_payout(str(released)) == "rate_unavailable"

    assert "event=stokvel.payout_rate_unavailable" in caplog.text
    assert _payout(session_factory, released).remittance_status == "pending"
    assert _counts(session_factory) == {"quotes": 0, "remittances": 0}


def test_a_missing_platform_account_is_failed_not_retried_forever(
    session_factory, payee, released, rates
):
    with session_factory() as session:
        session.execute(delete(Account).where(Account.account_id == payee["issuer"]))
        session.commit()

    assert settle_payout(str(released)) == "failed"

    payout = _payout(session_factory, released)
    assert (payout.remittance_status, payout.quote_id) == ("failed", None)
    assert _counts(session_factory) == {"quotes": 0, "remittances": 0}


def test_unknown_and_invalid_ids_are_skipped(session_factory, rates):
    assert settle_payout("not-a-uuid") == "skipped"
    assert settle_payout(str(uuid.uuid4())) == "skipped"


# --- price_stokvel_payout ----------------------------------------------------


def _price(session_factory, *args):
    with session_factory() as session:
        token = set_request_db_session(session)
        try:
            pricing, sender_amount = quote_service.price_stokvel_payout(*args)
            session.commit()
            return pricing, sender_amount
        finally:
            reset_request_db_session(token)


def test_a_payout_in_another_currency_is_converted_directly(session_factory, rates):
    pricing, sender_amount = _price(
        session_factory, Decimal("200"), CURRENCY_ZAR, CURRENCY_NAD
    )

    assert sender_amount == Decimal("3700.00")
    assert pricing.token_amount == Decimal("200")  # the pool, exactly
    assert pricing.receiver_amount == Decimal("3515.00")  # 3700 x 0.95
    assert (pricing.sender_transaction_fee, pricing.exchange_rate_margin) == (0, 0)
    assert pricing.receiver_payout_estimate == (
        pricing.receiver_amount - pricing.receiver_payout_fee
    )


def test_a_usd_stokvel_needs_no_token_rate(session_factory, rates):
    pricing, sender_amount = _price(
        session_factory, Decimal("200"), CURRENCY_USD, CURRENCY_USD
    )

    assert sender_amount == Decimal("200.00")
    assert pricing.fiat_to_token_exchange_rate_id is None
    assert pricing.receiver_amount == Decimal("200.00")


def test_a_pool_must_be_positive(session_factory, rates):
    with pytest.raises(ValueError):
        _price(session_factory, Decimal("0"), CURRENCY_ZAR, CURRENCY_ZAR)


# --- queue_released_payouts --------------------------------------------------


def test_a_released_payout_is_queued_once_then_not_again_for_a_while(
    session_factory, released, queued
):
    assert queue_released_payouts() == 1
    assert queued == [str(released)]

    assert queue_released_payouts() == 0  # queued just now
    assert queued == [str(released)]


def test_a_payout_still_waiting_is_queued_again_later(
    session_factory, released, queued
):
    queue_released_payouts()
    with session_factory() as session:
        session.execute(
            update(StokvelPayout)
            .where(StokvelPayout.id == released)
            .values(
                updated_at=datetime.now(UTC)
                - stokvel_payouts.REQUEUE_AFTER
                - timedelta(seconds=1)
            )
        )
        session.commit()

    assert queue_released_payouts() == 1
    assert queued == [str(released)] * 2


def test_a_payout_already_started_or_not_released_is_not_queued(
    session_factory, cycle, released, queued, rates
):
    settle_payout(str(released))
    with session_factory() as session:
        ensure_payout(session, cycle["id"], 1)  # pending, not released
        session.commit()

    assert queue_released_payouts() == 0
    assert queued == []


def test_the_longest_waiting_payouts_go_first(
    session_factory, cycle, released, queued, monkeypatch
):
    """With more due than one run queues, the one queued longest ago goes
    first, so a few that keep failing cannot keep the rest out."""
    _fund(session_factory, cycle)
    _record(session_factory, cycle, 1)
    with session_factory() as session:
        round_1 = session.scalar(
            select(StokvelPayout.id).where(StokvelPayout.round == 1)
        )
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        session.execute(
            update(StokvelPayout)
            .where(StokvelPayout.id == round_1)
            .values(updated_at=long_ago)
        )
        session.commit()
    monkeypatch.setattr(stokvel_payouts, "_QUEUE_LIMIT", 1)

    assert queue_released_payouts() == 1
    assert queued == [str(round_1)]
