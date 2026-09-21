import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_EXTERNAL,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services import remittance_service
from remitx_api.services.remittance_service import (
    REMITX_TREASURY_WALLET_LABEL,
    UCTUSD_ISSUER_LABEL,
)

ENDPOINT = "/remittances"


@pytest.fixture(autouse=True)
def no_real_enqueue(monkeypatch):
    """Every test here confirms a remittance, which enqueues to Redis — none
    is running in CI, so this is patched for the whole module."""
    monkeypatch.setattr(
        remittance_service.queue_service, "enqueue_settle_remittance", lambda *_: None
    )


def _seed(client, sender_id):
    """Rate data, platform accounts, a funded sender, and a beneficiary —
    everything `POST /remittances` needs, mirroring test_quotes_route.py's
    `_seed`."""
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
                ExchangeRate(
                    base_currency="ZAR",
                    quote_currency="ZWL",
                    rate=Decimal("16.22"),
                    fetched_at=now,
                    valid_until=now + timedelta(hours=1),
                ),
            ]
        )

        admin = UserController().ensure_provisioned(
            "user_admin_remit_route", lambda: "admin-remit@example.com", lambda: "Admin"
        )
        db.session.add_all(
            [
                Account(
                    user_id=admin.id,
                    type=TYPE_PLATFORM_FIAT,
                    account_currency=CURRENCY_ZAR,
                    label="RemitX SA Bank Account",
                ),
                Account(
                    user_id=admin.id,
                    type=TYPE_PLATFORM_REVENUE,
                    account_currency=CURRENCY_ZAR,
                    label="RemitX SA Fee Revenue",
                ),
                Account(
                    user_id=admin.id,
                    type=TYPE_PLATFORM_FIAT,
                    account_currency=CURRENCY_ZWL,
                    label="RemitX ZIM Bank Account",
                ),
                Account(
                    user_id=admin.id,
                    type=TYPE_XRPL_WALLET,
                    account_currency=CURRENCY_TOKEN,
                    label=REMITX_TREASURY_WALLET_LABEL,
                ),
                Account(
                    user_id=None,
                    type=TYPE_EXTERNAL,
                    account_currency=CURRENCY_TOKEN,
                    label=UCTUSD_ISSUER_LABEL,
                ),
            ]
        )
        db.session.commit()

        recipient = UserController().ensure_provisioned(
            "user_remit_route_recipient",
            lambda: "remit-route-recipient@example.com",
            lambda: "Recip",
        )

        sender_zar = AccountRepository().get_user_account(sender_id, CURRENCY_ZAR)
        AccountRepository().increase_balance(sender_zar.account_id, Decimal("1000"))
        db.session.commit()

        return recipient.id
    finally:
        db.close_session(token)


def _create_quote(client, recipient_id, amount="1000"):
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

    quote_response = client.post(
        "/quotes/create-quote",
        json={
            "beneficiary_id": beneficiary_id,
            "sender_amount": amount,
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )
    assert quote_response.status_code == 200
    return quote_response.json()["quote_id"]


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(ENDPOINT, json={"quote_id": str(uuid.uuid4())})

    assert response.status_code == 401


def test_confirm_end_to_end(verified_client):
    client, sender = verified_client
    recipient_id = _seed(client, sender.id)
    quote_id = _create_quote(client, recipient_id)

    response = client.post(ENDPOINT, json={"quote_id": quote_id})

    assert response.status_code == 200
    body = response.json()
    assert body["quote_id"] == quote_id
    assert body["status"] == "pending"
    assert body["sender_amount"] == "1000.00000000"


def test_unknown_quote_is_a_400(verified_client):
    client, sender = verified_client
    _seed(client, sender.id)

    response = client.post(ENDPOINT, json={"quote_id": str(uuid.uuid4())})

    assert response.status_code == 400


def test_confirming_twice_is_a_409(verified_client):
    client, sender = verified_client
    recipient_id = _seed(client, sender.id)
    quote_id = _create_quote(client, recipient_id)

    first = client.post(ENDPOINT, json={"quote_id": quote_id})
    assert first.status_code == 200

    second = client.post(ENDPOINT, json={"quote_id": quote_id})
    assert second.status_code == 409
