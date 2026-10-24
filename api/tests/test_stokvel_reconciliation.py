"""Pool reconciliation (R3-08, #245).

One `token_burn` per quote, the burn equal to the round's pool while the
treasury still holds float, and the ledger float after three rounds.
"""

# Fixtures are imported by name, which pytest needs and ruff reads as unused
# or redefined when a test asks for them.
# ruff: noqa: F401, F811

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EXTERNAL,
    TYPE_STOKVEL,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.platform_account_seed import (
    ISSUER_LABEL,
    TREASURY_WALLET_LABEL,
)
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.stokvel_payout import StokvelPayout
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    TYPE_REMITTANCE,
    TYPE_STOKVEL_CONTRIBUTION,
    TYPE_STOKVEL_POOL_RELEASE,
    TYPE_TOKEN_BURN,
    TYPE_TREASURY_FUNDING,
    Transaction,
)
from remitx_api.services import queue_service
from remitx_api.services.stokvel_reconciliation_service import check_pool_reconciliation
from remitx_worker.stokvel_payouts import settle_payout
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tests.kyc_helpers import make_user
from tests.platform_account_helpers import seed_platform_accounts
from tests.test_worker_stokvel_contribution import pending, session_factory
from tests.test_worker_stokvel_release import POOL, cycle
from tests.test_worker_stokvel_settle_payout import payee, rates, released

FLOAT = Decimal("1000")
CONTRIBUTION = POOL / 2


def _quiet_hand_off(monkeypatch) -> None:
    monkeypatch.setattr(
        queue_service, "enqueue_settle_remittance", lambda quote_id: None
    )


def test_a_second_burn_for_the_quote_is_refused(
    session_factory, cycle, payee, released, rates, monkeypatch
):
    """The partial index, not the application guard.

    Another `remittance` leg on the same quote must still insert. If the
    index were missing, the second burn would insert and this fails. If it
    were unique on every type, the extra remittance would fail.
    """
    _quiet_hand_off(monkeypatch)
    assert settle_payout(str(released)) == "created"

    with session_factory() as session:
        quote_id = session.get(StokvelPayout, released).quote_id
        burn = session.scalar(
            select(Transaction).where(Transaction.type == TYPE_TOKEN_BURN)
        )
        session.add(
            Transaction(
                type=TYPE_REMITTANCE,
                credit_account_id=burn.credit_account_id,
                debit_account_id=burn.debit_account_id,
                amount=burn.amount,
                currency=burn.currency,
                status=STATUS_PENDING,
                quote_id=quote_id,
            )
        )
        session.commit()

    with session_factory() as session:
        burn = session.scalar(
            select(Transaction).where(Transaction.type == TYPE_TOKEN_BURN)
        )
        session.add(
            Transaction(
                type=TYPE_TOKEN_BURN,
                credit_account_id=burn.credit_account_id,
                debit_account_id=burn.debit_account_id,
                amount=burn.amount,
                currency=burn.currency,
                status=STATUS_PENDING,
                quote_id=burn.quote_id,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_the_burn_is_the_pool_and_not_the_float(
    session_factory, cycle, payee, released, rates, monkeypatch
):
    """The wallet holds float for other remittances. The burn is the pool."""
    with session_factory() as session:
        session.execute(
            update(Account)
            .where(Account.account_id == cycle["accounts"]["treasury"])
            .values(account_balance=FLOAT)
        )
        session.commit()
    _quiet_hand_off(monkeypatch)

    assert settle_payout(str(released)) == "created"

    with session_factory() as session:
        burn = session.scalar(
            select(Transaction).where(Transaction.type == TYPE_TOKEN_BURN)
        )
        treasury = session.get(Account, cycle["accounts"]["treasury"])
        assert burn.amount == POOL
        assert treasury.account_balance == FLOAT
        assert burn.amount < treasury.account_balance


def _quote_id() -> uuid.UUID:
    """A quote a burn can hang off. One burn per quote."""
    now = datetime.now(UTC)
    sender = make_user()
    rate = ExchangeRate(
        base_currency=CURRENCY_ZAR,
        quote_currency=CURRENCY_ZAR,
        rate=Decimal("1"),
        fetched_at=now,
        valid_until=now + timedelta(hours=1),
    )
    db.session.add(rate)
    db.session.flush()
    quote = Quote(
        sender_user_id=sender.id,
        beneficiary_user_id=make_user().id,
        sender_amount=POOL,
        sender_currency=CURRENCY_ZAR,
        sender_transaction_fee=Decimal("0"),
        token_amount=POOL,
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate=Decimal("1"),
        fiat_exchange_rate_id=rate.id,
        fiat_exchange_rate=Decimal("1"),
        exchange_rate_margin=Decimal("0"),
        receiver_amount=POOL,
        receiver_currency=CURRENCY_ZAR,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=POOL,
        expires_at=now + timedelta(minutes=15),
    )
    db.session.add(quote)
    db.session.flush()
    return quote.quote_id


def _leg(
    type_, source, destination, amount, *, status=STATUS_CONFIRMED, quote_id=None
) -> None:
    db.session.add(
        Transaction(
            type=type_,
            credit_account_id=source,
            debit_account_id=destination,
            amount=amount,
            currency=CURRENCY_TOKEN,
            status=status,
            quote_id=quote_id,
        )
    )


def test_three_rounds_match_and_an_overburn_does_not(app_context):
    """Three released rounds leave the float. Tokens still in the contract
    are not counted as treasury UCTUSD. A pending burn changes nothing."""
    seeded = seed_platform_accounts()
    treasury = seeded[TREASURY_WALLET_LABEL].account_id
    issuer = seeded[ISSUER_LABEL].account_id
    stokvel = Account(
        type=TYPE_STOKVEL,
        account_currency=CURRENCY_TOKEN,
        label="Stokvel pool",
        user_id=None,
    )
    beneficiary = Account(
        type=TYPE_EXTERNAL,
        account_currency=CURRENCY_TOKEN,
        label="Beneficiary token",
        user_id=None,
    )
    db.session.add_all([stokvel, beneficiary])
    db.session.flush()

    _leg(TYPE_TREASURY_FUNDING, issuer, treasury, FLOAT)
    for _round in range(3):
        _leg(TYPE_STOKVEL_CONTRIBUTION, treasury, stokvel.account_id, CONTRIBUTION)
        _leg(TYPE_STOKVEL_CONTRIBUTION, treasury, stokvel.account_id, CONTRIBUTION)
        _leg(TYPE_STOKVEL_POOL_RELEASE, stokvel.account_id, treasury, POOL)
        _leg(TYPE_REMITTANCE, treasury, beneficiary.account_id, POOL)
        _leg(TYPE_REMITTANCE, beneficiary.account_id, treasury, POOL)
        _leg(TYPE_TOKEN_BURN, treasury, issuer, POOL, quote_id=_quote_id())
    db.session.flush()

    done = check_pool_reconciliation(FLOAT - 3 * POOL)
    assert done.matches
    assert done.contract_held == Decimal("0")

    _leg(TYPE_STOKVEL_CONTRIBUTION, treasury, stokvel.account_id, CONTRIBUTION)
    stokvel.account_balance = CONTRIBUTION
    db.session.flush()

    held = FLOAT - 3 * POOL - CONTRIBUTION
    open_round = check_pool_reconciliation(held)
    assert open_round.matches
    assert open_round.expected == held
    assert open_round.contract_held == CONTRIBUTION
    assert not check_pool_reconciliation(held - 1).matches

    _leg(
        TYPE_TOKEN_BURN,
        treasury,
        issuer,
        Decimal("50"),
        status=STATUS_PENDING,
        quote_id=_quote_id(),
    )
    db.session.flush()
    assert check_pool_reconciliation(held).matches
