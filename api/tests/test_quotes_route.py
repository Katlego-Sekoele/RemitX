import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.repositories.account_repository import AccountRepository

ENDPOINT = "/quotes"


def _seed(client):
    """Store a rate and a beneficiary for `verified_client`'s persisted
    sender, funding their ZAR account — all under one raw session, since the
    per-request session `client.post` opens is separate.
    """
    token = db.open_session()
    try:
        now = datetime.now(UTC)
        db.session.add_all(
            [
                ExchangeRate(
                    base_currency="USD",
                    quote_currency="ZAR",
                    rate=Decimal("18.50"),
                    fetched_at=now,
                    valid_until=now + timedelta(hours=1),
                ),
                # Direct cross leg — the beneficiary's ZWL payout currency,
                # required now that fiat_exchange_rate is never null.
                ExchangeRate(
                    base_currency="ZAR",
                    quote_currency="ZWL",
                    rate=Decimal("16.22"),
                    fetched_at=now,
                    valid_until=now + timedelta(hours=1),
                ),
            ]
        )
        db.session.commit()

        recipient = UserController().ensure_provisioned(
            "user_quotes_route_recipient",
            lambda: "recipient@example.com",
            lambda: "Recip",
        )
        AccountRepository().get_or_create_user_account(
            recipient.id, recipient.base_reference, "ZWL"
        )
        db.session.commit()
        return recipient.id
    finally:
        db.close_session(token)


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(f"{ENDPOINT}/create-quote", json={})

    assert response.status_code == 401


def test_create_quote_end_to_end(verified_client):
    client, sender = verified_client
    recipient_id = _seed(client)

    beneficiary_response = client.post(
        "/beneficiaries/create-beneficiary",
        json={
            "linked_user_id": str(recipient_id),
            "payout_currency": "ZWL",
            "relationship": "sibling",
        },
    )
    assert beneficiary_response.status_code == 200
    beneficiary_id = beneficiary_response.json()["beneficiary_id"]

    token = db.open_session()
    try:
        sender_zar = AccountRepository().get_user_account(sender.id, CURRENCY_ZAR)
        AccountRepository().increase_balance(sender_zar.account_id, Decimal("1000"))
        db.session.commit()
    finally:
        db.close_session(token)

    response = client.post(
        f"{ENDPOINT}/create-quote",
        json={
            "beneficiary_id": beneficiary_id,
            "sender_amount": "1000",
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sender_amount"] == "1000.00000000"
    assert body["status"] == "ACTIVE"
    assert Decimal(body["sender_transaction_fee"]) == Decimal("20.00000000")


def test_insufficient_balance_is_a_400(verified_client):
    client, sender = verified_client
    recipient_id = _seed(client)

    beneficiary_response = client.post(
        "/beneficiaries/create-beneficiary",
        json={
            "linked_user_id": str(recipient_id),
            "payout_currency": "ZWL",
            "relationship": "sibling",
        },
    )
    beneficiary_id = beneficiary_response.json()["beneficiary_id"]

    # No balance was ever added to the sender's ZAR account.
    response = client.post(
        f"{ENDPOINT}/create-quote",
        json={
            "beneficiary_id": beneficiary_id,
            "sender_amount": "100",
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )

    assert response.status_code == 400


def test_caller_not_in_the_database_is_a_400(client):
    """`client` (unlike `verified_client`) overrides `get_current_user` with a
    transient `User` that was never written to the database — `client`'s own
    fixture docstring flags this. `quote_service.create_quote` looks the
    sender up by id and finds nothing, the same outcome an UNVERIFIED caller
    would eventually hit further down, just one check earlier.
    """
    response = client.post(
        f"{ENDPOINT}/create-quote",
        json={
            "beneficiary_id": str(uuid.uuid4()),
            "sender_amount": "100",
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )

    assert response.status_code == 400


def test_preview_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(
        f"{ENDPOINT}/preview-quote",
        json={
            "sender_amount": "1000",
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )

    assert response.status_code == 401


def test_preview_end_to_end_no_beneficiary_needed(verified_client):
    """The preview endpoint doesn't touch a beneficiary, a sender account, or
    any balance — just the two currencies and an amount."""
    client, _sender = verified_client
    token = db.open_session()
    try:
        now = datetime.now(UTC)
        db.session.add_all(
            [
                ExchangeRate(
                    base_currency="USD",
                    quote_currency="ZAR",
                    rate=Decimal("18.50"),
                    fetched_at=now,
                    valid_until=now + timedelta(hours=1),
                ),
                # Direct cross leg — fetched as its own pair, not derived.
                ExchangeRate(
                    base_currency="ZAR",
                    quote_currency="USD",
                    rate=Decimal("0.054"),
                    fetched_at=now,
                    valid_until=now + timedelta(hours=1),
                ),
            ]
        )
        db.session.commit()
    finally:
        db.close_session(token)

    response = client.post(
        f"{ENDPOINT}/preview-quote",
        json={
            "sender_amount": "1000",
            "sender_currency": "ZAR",
            "receiver_payout_currency": "USD",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["sender_currency"] == "ZAR"
    assert body["fiat_to_token_exchange_rate"] == "0.05405405"
    assert Decimal(body["sender_transaction_fee"]) == Decimal("20.00000000")
    assert body["receiver_payout_currency"] == "USD"
    assert body["fiat_exchange_rate"] == "0.05400000"
    assert "quote_id" not in body


def test_preview_unsupported_currency_is_a_400(verified_client):
    client, _sender = verified_client

    response = client.post(
        f"{ENDPOINT}/preview-quote",
        json={
            "sender_amount": "1000",
            "sender_currency": "EUR",
            "receiver_payout_currency": "ZAR",
        },
    )

    assert response.status_code == 400
