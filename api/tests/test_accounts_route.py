import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_TOKEN,
    CURRENCY_USD,
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
    TOKEN_ISSUER_LABEL,
)

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
        assert account["balance"] == "0.00"
        assert account["available_balance"] == "0.00"


def test_accounts_carry_their_reference_and_kind(verified_client):
    client, sender = verified_client

    accounts = {a["currency"]: a for a in client.get(ACCOUNTS).json()}

    base = sender.base_reference
    assert accounts[CURRENCY_ZAR]["reference"] == f"{base}-zar"
    assert accounts[CURRENCY_ZAR]["kind"] == "fiat"
    assert accounts[CURRENCY_TOKEN]["reference"] == f"{base}-tok"
    assert accounts[CURRENCY_TOKEN]["kind"] == "settlement"


def test_accounts_list_zar_then_other_fiat_alphabetically_then_settlement(
    verified_client,
):
    client, sender = verified_client
    token = db.open_session()
    try:
        repository = AccountRepository()
        # Opened out of order, so the response can't just be insertion order.
        for currency in (CURRENCY_ZWL, CURRENCY_NAD, CURRENCY_USD):
            repository.get_or_create_user_account(
                sender.id, sender.base_reference, currency
            )
        db.session.commit()
    finally:
        db.close_session(token)

    body = client.get(ACCOUNTS).json()

    assert [a["currency"] for a in body] == [
        CURRENCY_ZAR,
        CURRENCY_NAD,
        CURRENCY_USD,
        CURRENCY_ZWL,
        CURRENCY_TOKEN,
    ]
    assert [a["kind"] for a in body] == ["fiat"] * 4 + ["settlement"]


def test_accounts_only_ever_lists_the_callers_own(verified_client):
    client, sender = verified_client
    token = db.open_session()
    try:
        UserController().ensure_provisioned(
            "user_accounts_someone_else",
            lambda: "someone-else@example.com",
            lambda: "Someone",
        )
        db.session.commit()
    finally:
        db.close_session(token)

    body = client.get(ACCOUNTS).json()

    assert len(body) == 2
    assert all(a["reference"].startswith(f"{sender.base_reference}-") for a in body)


def test_a_pending_send_shows_as_the_gap_between_balance_and_available(
    verified_client, monkeypatch
):
    client, sender = verified_client
    _send_remittance(client, sender, monkeypatch, funded="1500", amount="1000")

    zar = {a["currency"]: a for a in client.get(ACCOUNTS).json()}[CURRENCY_ZAR]

    # The ledger still holds the full 1500 until settlement confirms the legs;
    # the 1000 in flight is already spoken for.
    assert zar["balance"] == "1500.00"
    assert zar["available_balance"] == "500.00"


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


def _send_remittance(client, sender, monkeypatch, funded="1000", amount="1000"):
    """Seed the platform accounts and rates, fund the sender's ZAR account
    with `funded`, and confirm a ZAR -> ZWL send of `amount` to a new
    recipient. Settlement is left queued. Returns the quote's JSON and the
    recipient's id."""
    monkeypatch.setattr(
        remittance_service.queue_service, "enqueue_settle_remittance", lambda *_: None
    )
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
                    label=TOKEN_ISSUER_LABEL,
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
        AccountRepository().increase_balance(sender_zar.account_id, Decimal(funded))
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
        json={
            "beneficiary_id": beneficiary_id,
            "sender_amount": amount,
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )
    quote_id = quote_response.json()["quote_id"]

    confirm_response = client.post("/remittances", json={"quote_id": quote_id})
    assert confirm_response.status_code == 200
    return quote_response.json(), recipient_id


def test_a_remittance_shows_up_correctly_on_both_sides(verified_client, monkeypatch):
    client, sender = verified_client
    quote, _recipient_id = _send_remittance(client, sender, monkeypatch)

    accounts = {a["currency"]: a for a in client.get(ACCOUNTS).json()}

    # Sender's ZAR is still 1000 raw, but the two pending legs (30 fee, 970
    # net) already count against *available* balance.
    zar_account = accounts[CURRENCY_ZAR]
    assert zar_account["balance"] == "1000.00"
    assert zar_account["available_balance"] == "0.00"
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
    token_amount = Decimal(quote["token_amount"])
    assert Decimal(token_account["available_balance"]) == -token_amount
    token_legs = client.get(
        HISTORY, params={"account_id": token_account["account_id"]}
    ).json()
    assert len(token_legs) == 2
    directions = {leg["direction"] for leg in token_legs}
    assert directions == {"in", "out"}
