import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
    TYPE_XRPL_WALLET,
    Account,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services import remittance_service
from remitx_api.services.remittance_service import REMITX_TREASURY_WALLET_LABEL

ACCOUNTS = "/accounts"
HISTORY = "/accounts-history"


def test_accounts_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.get(ACCOUNTS)

    assert response.status_code == 401


def test_history_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.get(HISTORY, params={"account_id": str(uuid.uuid4())})

    assert response.status_code == 401


def test_new_user_has_two_accounts_with_zero_available_balance(verified_client):
    client, _sender = verified_client

    response = client.get(ACCOUNTS)

    assert response.status_code == 200
    body = response.json()
    currencies = {account["currency"] for account in body}
    assert currencies == {CURRENCY_ZAR, CURRENCY_TOKEN}
    for account in body:
        # Decimal("0.00000000")'s adjusted exponent (-8) trips Python's
        # decimal-to-string rule into scientific notation even at zero.
        assert account["available_balance"] == "0E-8"


def test_history_for_an_unknown_account_is_a_400(verified_client):
    client, _sender = verified_client

    response = client.get(HISTORY, params={"account_id": str(uuid.uuid4())})

    assert response.status_code == 400


def test_history_for_someone_elses_account_is_a_400(verified_client):
    client, _sender = verified_client
    token = db.open_session()
    try:
        other = UserController().ensure_provisioned(
            "user_accounts_other", lambda: "other-accounts@example.com", lambda: "Other"
        )
        other_zar_id = (
            AccountRepository().get_user_account(other.id, CURRENCY_ZAR).account_id
        )
    finally:
        db.close_session(token)

    response = client.get(HISTORY, params={"account_id": str(other_zar_id)})

    assert response.status_code == 400


def test_a_remittance_shows_up_correctly_on_both_sides(verified_client, monkeypatch):
    monkeypatch.setattr(
        remittance_service.queue_service, "enqueue_settle_remittance", lambda *_: None
    )
    client, sender = verified_client

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
            "user_admin_accounts_route",
            lambda: "admin-accounts@example.com",
            lambda: "Adm",
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
                    type=TYPE_XRPL_WALLET,
                    account_currency=CURRENCY_TOKEN,
                    label=REMITX_TREASURY_WALLET_LABEL,
                ),
            ]
        )
        db.session.commit()

        recipient = UserController().ensure_provisioned(
            "user_accounts_route_recipient",
            lambda: "accounts-route-recipient@example.com",
            lambda: "Recip",
        )

        sender_zar = AccountRepository().get_user_account(sender.id, CURRENCY_ZAR)
        AccountRepository().increase_balance(sender_zar.account_id, Decimal("1000"))
        db.session.commit()
        recipient_id = recipient.id
    finally:
        db.close_session(token)

    beneficiary_response = client.post(
        "/beneficiaries/create-beneficiary",
        json={
            "linked_user_id": str(recipient_id),
            "payout_currency": "ZWL",
            "relationship": "sibling",
        },
    )
    beneficiary_id = beneficiary_response.json()["beneficiary_id"]
    quote_response = client.post(
        "/quotes/create-quote",
        json={"beneficiary_id": beneficiary_id, "sender_amount": "1000"},
    )
    quote_id = quote_response.json()["quote_id"]

    confirm_response = client.post("/remittances", json={"quote_id": quote_id})
    assert confirm_response.status_code == 200

    accounts = {a["currency"]: a for a in client.get(ACCOUNTS).json()}

    # Sender's ZAR is still 1000 raw, but the two pending legs (30 fee, 970
    # net) already count against *available* balance.
    zar_account = accounts[CURRENCY_ZAR]
    assert zar_account["available_balance"] == "0E-8"
    zar_legs = client.get(
        HISTORY, params={"account_id": zar_account["account_id"]}
    ).json()
    assert len(zar_legs) == 2
    assert all(leg["direction"] == "out" for leg in zar_legs)
    assert all(leg["status"] == "pending" for leg in zar_legs)

    # Sender's token account never actually receives anything until
    # settlement — its only pending leg is the outgoing one to the
    # beneficiary, so available balance goes negative by that amount.
    token_account = accounts[CURRENCY_TOKEN]
    token_amount = Decimal(quote_response.json()["token_amount"])
    assert Decimal(token_account["available_balance"]) == -token_amount
    token_legs = client.get(
        HISTORY, params={"account_id": token_account["account_id"]}
    ).json()
    assert len(token_legs) == 2
    directions = {leg["direction"] for leg in token_legs}
    assert directions == {"in", "out"}
