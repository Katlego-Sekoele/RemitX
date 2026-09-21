"""The worker half of remittance settlement (Transaction_Flow_Context.md §2
Phase C).

Runs the task function directly against a scratch SQLite file — no broker
involved, mirroring test_integration_message_task.py exactly.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.extensions import Base, build_engine
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_EXTERNAL,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_USER,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    TYPE_FEE,
    TYPE_REMITTANCE,
    Transaction,
)
from remitx_api.models.orm.user import User
from remitx_worker import db as worker_db
from remitx_worker.tasks import settle_remittance
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session_factory(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    worker_db.configure(factory)
    yield factory
    worker_db.configure(None)


def _user(session) -> uuid.UUID:
    user_id = uuid.uuid4()
    session.add(
        User(
            id=user_id,
            clerk_user_id=f"user_{user_id}",
            base_reference=f"wrk{user_id.int}",
        )
    )
    session.commit()
    return user_id


def _account(session, *, type_, currency, balance="0", label=None) -> uuid.UUID:
    account_id = uuid.uuid4()
    account = Account(
        account_id=account_id,
        user_id=None if type_ == TYPE_EXTERNAL else _user(session),
        type=type_,
        reference=f"{account_id}-{currency}" if type_ == TYPE_USER else None,
        account_currency=currency,
        account_balance=Decimal(balance),
        label=label or f"{type_} {currency}",
    )
    session.add(account)
    session.commit()
    return account.account_id


def _quote(session, *, sender_account_id, beneficiary_account_id) -> uuid.UUID:
    """A `Quote` row purely to satisfy `transactions.quote_id`'s FK —
    `settle_remittance` never reads `Quote` itself, so the priced fields
    here are arbitrary but valid."""
    now = datetime.now(UTC)
    rate = ExchangeRate(
        base_currency=CURRENCY_ZAR,
        quote_currency=CURRENCY_ZAR,
        rate=Decimal("1"),
        fetched_at=now,
        valid_until=now + timedelta(hours=1),
    )
    session.add(rate)
    session.commit()

    quote = Quote(
        sender_account_id=sender_account_id,
        beneficiary_account_id=beneficiary_account_id,
        sender_amount=Decimal("1000"),
        sender_currency=CURRENCY_ZAR,
        sender_transaction_fee=Decimal("20"),
        token_amount=Decimal("52.432432"),
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate=Decimal("0.05"),
        fiat_exchange_rate_id=rate.id,
        fiat_exchange_rate=Decimal("1"),
        exchange_rate_margin=Decimal("10"),
        receiver_amount=Decimal("970"),
        receiver_currency=CURRENCY_ZAR,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=Decimal("970"),
        expires_at=now + timedelta(minutes=15),
    )
    session.add(quote)
    session.commit()
    return quote.quote_id


def _pending_leg(
    session, *, quote_id, credit_account_id, debit_account_id, amount, currency, type_
) -> uuid.UUID:
    tx = Transaction(
        tx_id=uuid.uuid4(),
        type=type_,
        credit_account_id=credit_account_id,
        debit_account_id=debit_account_id,
        amount=Decimal(amount),
        currency=currency,
        status=STATUS_PENDING,
        quote_id=quote_id,
    )
    session.add(tx)
    session.commit()
    return tx.tx_id


@pytest.fixture
def pending_remittance(session_factory):
    """A quote's four pending legs (Transaction_Flow_Context.md §2 Phase
    B2's worked example: 1000 sent, 30 fee, 970 net, 52.432432 tokens),
    seeded directly against the scratch DB. Returns
    (quote_id, sender_zar, sender_token, fee_revenue, bank, treasury,
    beneficiary_token).
    """
    with session_factory() as session:
        sender_zar = _account(session, type_=TYPE_USER, currency=CURRENCY_ZAR)
        sender_token = _account(session, type_=TYPE_USER, currency=CURRENCY_TOKEN)
        beneficiary_token = _account(session, type_=TYPE_USER, currency=CURRENCY_TOKEN)
        fee_revenue = _account(
            session, type_=TYPE_PLATFORM_REVENUE, currency=CURRENCY_ZAR
        )
        bank = _account(session, type_=TYPE_PLATFORM_FIAT, currency=CURRENCY_ZAR)
        treasury = _account(
            session,
            type_=TYPE_XRPL_WALLET,
            currency=CURRENCY_TOKEN,
            balance="1000",
        )
        quote_id = _quote(
            session,
            sender_account_id=sender_zar,
            beneficiary_account_id=beneficiary_token,
        )

        _pending_leg(
            session,
            quote_id=quote_id,
            credit_account_id=sender_zar,
            debit_account_id=fee_revenue,
            amount="30",
            currency=CURRENCY_ZAR,
            type_=TYPE_FEE,
        )
        _pending_leg(
            session,
            quote_id=quote_id,
            credit_account_id=sender_zar,
            debit_account_id=bank,
            amount="970",
            currency=CURRENCY_ZAR,
            type_=TYPE_REMITTANCE,
        )
        _pending_leg(
            session,
            quote_id=quote_id,
            credit_account_id=treasury,
            debit_account_id=sender_token,
            amount="52.432432",
            currency=CURRENCY_TOKEN,
            type_=TYPE_REMITTANCE,
        )
        _pending_leg(
            session,
            quote_id=quote_id,
            credit_account_id=sender_token,
            debit_account_id=beneficiary_token,
            amount="52.432432",
            currency=CURRENCY_TOKEN,
            type_=TYPE_REMITTANCE,
        )

    return {
        "quote_id": quote_id,
        "sender_zar": sender_zar,
        "sender_token": sender_token,
        "fee_revenue": fee_revenue,
        "bank": bank,
        "treasury": treasury,
        "beneficiary_token": beneficiary_token,
    }


def _balance(session_factory, account_id) -> Decimal:
    with session_factory() as session:
        return session.get(Account, account_id).account_balance


def _legs(session_factory, quote_id) -> list[Transaction]:
    with session_factory() as session:
        return session.query(Transaction).filter(Transaction.quote_id == quote_id).all()


def test_settling_confirms_all_four_legs(session_factory, pending_remittance):
    result = settle_remittance(str(pending_remittance["quote_id"]))

    assert result == "settled"
    legs = _legs(session_factory, pending_remittance["quote_id"])
    assert len(legs) == 4
    assert all(leg.status == STATUS_CONFIRMED for leg in legs)
    assert all(leg.confirmed_at is not None for leg in legs)


def test_settling_credits_the_right_four_accounts(session_factory, pending_remittance):
    settle_remittance(str(pending_remittance["quote_id"]))

    assert _balance(session_factory, pending_remittance["fee_revenue"]) == Decimal("30")
    assert _balance(session_factory, pending_remittance["bank"]) == Decimal("970")
    # Treasury started at 1000, paid out 52.432432 to the sender's token
    # account as the pass-through leg's destination.
    assert _balance(session_factory, pending_remittance["sender_token"]) == Decimal(
        "52.432432"
    )
    assert _balance(
        session_factory, pending_remittance["beneficiary_token"]
    ) == Decimal("52.432432")


def test_settling_twice_does_not_double_credit(session_factory, pending_remittance):
    """The graded requirement: a redelivered settlement message must not
    credit the recipient more than once."""
    first = settle_remittance(str(pending_remittance["quote_id"]))
    assert first == "settled"
    balance_after_first = _balance(
        session_factory, pending_remittance["beneficiary_token"]
    )

    second = settle_remittance(str(pending_remittance["quote_id"]))

    assert second == "skipped"
    assert (
        _balance(session_factory, pending_remittance["beneficiary_token"])
        == balance_after_first
    )
    assert _balance(session_factory, pending_remittance["fee_revenue"]) == Decimal("30")


def test_unknown_quote_is_skipped(session_factory):
    assert settle_remittance(str(uuid.uuid4())) == "skipped"


@pytest.mark.parametrize(
    "quote_id", ["not-a-uuid", "", None], ids=["junk", "empty", "none"]
)
def test_malformed_quote_id_is_skipped_not_an_error(session_factory, quote_id):
    assert settle_remittance(quote_id) == "skipped"
