"""The customer dashboard: limits, activity, in-flight transfers, beneficiaries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, CURRENCY_ZAR
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.models.orm.remittance import Remittance
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    TYPE_REMITTANCE,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from tests.kyc_helpers import make_user

DASHBOARD = "/dashboard"


def test_dashboard_anonymous_caller_is_rejected(anonymous_client):
    assert anonymous_client.get(DASHBOARD).status_code == 401


def test_dashboard_is_empty_until_the_caller_sends(verified_client):
    client, _sender = verified_client

    body = client.get(DASHBOARD).json()

    assert body["has_transfers"] is False
    assert body["in_flight"] == []
    assert body["beneficiaries"] == []
    assert body["limits"]["daily_sent_zar"] == "0.00"
    assert body["limits"]["monthly_sent_zar"] == "0.00"
    assert body["limits"]["daily_limit_zar"] == "3000.00"
    assert body["limits"]["monthly_limit_zar"] == "25000.00"
    assert len(body["activity"]) == 30
    assert all(day["zar_sent"] == "0.00" for day in body["activity"])
    assert all(day["token_received"] == "0.00" for day in body["activity"])


def test_dashboard_counts_sends_and_leaves_out_failures(verified_client):
    client, sender = verified_client
    token = db.open_session()
    try:
        beneficiary = make_user("dash-beneficiary")
        beneficiary.first_name = "Amahle"
        beneficiary.last_name = "Dlamini"
        _transfer(
            sender,
            beneficiary,
            sender_amount=Decimal("1000"),
            token_amount=Decimal("50"),
            status=STATUS_CONFIRMED,
        )
        _transfer(
            sender,
            beneficiary,
            sender_amount=Decimal("100"),
            token_amount=Decimal("5"),
            status=STATUS_PENDING,
        )
        _transfer(
            sender,
            beneficiary,
            sender_amount=Decimal("250"),
            token_amount=Decimal("12"),
            status=STATUS_FAILED,
        )
        db.session.commit()
    finally:
        db.close_session(token)

    body = client.get(DASHBOARD).json()
    today = datetime.now(UTC).date().isoformat()
    day = next(row for row in body["activity"] if row["day"] == today)

    assert body["has_transfers"] is True
    assert body["limits"]["daily_sent_zar"] == "1100.00"
    assert body["limits"]["monthly_sent_zar"] == "1100.00"
    assert day["zar_sent"] == "1100.00"
    assert day["token_received"] == "0.00"
    assert body["beneficiaries"] == [{"name": "Amahle D.", "zar_sent": "1100.00"}]
    assert len(body["in_flight"]) == 1
    inflight = body["in_flight"][0]
    assert inflight["direction"] == "sent"
    assert inflight["status"] == "pending"
    assert inflight["counterparty_name"] == "Amahle D."
    assert inflight["amount"] == "100.00"
    assert inflight["currency"] == CURRENCY_ZAR


def _transfer(sender, beneficiary, *, sender_amount, token_amount, status):
    now = datetime.now(UTC)
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
        beneficiary_user_id=beneficiary.id,
        sender_amount=sender_amount,
        sender_currency=CURRENCY_ZAR,
        sender_transaction_fee=Decimal("0"),
        token_amount=token_amount,
        token_name=CURRENCY_TOKEN,
        fiat_to_token_exchange_rate=Decimal("0.05"),
        fiat_exchange_rate_id=rate.id,
        fiat_exchange_rate=Decimal("1"),
        exchange_rate_margin=Decimal("0"),
        receiver_amount=sender_amount,
        receiver_currency=CURRENCY_ZAR,
        receiver_payout_fee=Decimal("0"),
        receiver_payout_estimate=sender_amount,
        expires_at=now + timedelta(minutes=15),
    )
    db.session.add(quote)
    db.session.flush()
    accounts = AccountRepository()
    source = accounts.get_or_create_user_account(
        sender.id, sender.base_reference, CURRENCY_TOKEN
    )
    destination = accounts.get_or_create_user_account(
        beneficiary.id, beneficiary.base_reference, CURRENCY_TOKEN
    )
    leg = Transaction(
        type=TYPE_REMITTANCE,
        credit_account_id=source.account_id,
        debit_account_id=destination.account_id,
        amount=token_amount,
        currency=CURRENCY_TOKEN,
        status=status,
        quote_id=quote.quote_id,
        confirmed_at=now if status == STATUS_CONFIRMED else None,
    )
    db.session.add(leg)
    db.session.flush()
    db.session.add(Remittance(quote_id=quote.quote_id, tx_id=leg.tx_id))
    db.session.flush()
