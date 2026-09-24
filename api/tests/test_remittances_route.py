import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.auth.dependencies import get_current_user
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
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services import remittance_service
from remitx_api.services.remittance_service import (
    REMITX_TREASURY_WALLET_LABEL,
    TOKEN_ISSUER_LABEL,
)
from remitx_worker import db as worker_db, tasks
from sqlalchemy.orm import sessionmaker

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
                    label=TOKEN_ISSUER_LABEL,
                ),
            ]
        )
        db.session.commit()

        recipient = UserController().ensure_provisioned(
            "user_remit_route_recipient",
            lambda: "remit-route-recipient@example.com",
            lambda: "Recip",
        )
        AccountRepository().get_or_create_user_account(
            recipient.id, recipient.base_reference, CURRENCY_ZWL
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
    if beneficiary_response.status_code == 409:
        # A second quote for the same person reuses the beneficiary. Main
        # refuses a duplicate add.
        listed = client.get("/beneficiaries/get-beneficiary-list")
        assert listed.status_code == 200
        beneficiary_id = next(
            row["beneficiary_id"]
            for row in listed.json()
            if row["linked_user_id"] == str(recipient_id)
        )
    else:
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


@pytest.fixture
def worker_on_app_db():
    """Point the worker's sessions at the app's in-memory database, so a
    worker task settles the group a request really created."""
    worker_db.configure(sessionmaker(bind=db.engine, autoflush=False))
    yield
    worker_db.configure(None)


def _act_as(client, user_id):
    """Swap who the client's requests come from."""
    client.app.dependency_overrides[get_current_user] = lambda: User(id=user_id)


def _confirmed_transfer(client, sender_id):
    recipient_id = _seed(client, sender_id)
    quote_id = _create_quote(client, recipient_id)
    response = client.post(ENDPOINT, json={"quote_id": quote_id})
    assert response.status_code == 200
    return recipient_id, quote_id, response.json()["remittance_id"]


def test_listing_is_login_only(anonymous_client):
    assert anonymous_client.get(ENDPOINT).status_code == 401


def test_the_sender_lists_and_reads_their_transfer(verified_client):
    client, sender = verified_client
    recipient_id, quote_id, remittance_id = _confirmed_transfer(client, sender.id)

    listed = client.get(ENDPOINT)
    one = client.get(f"{ENDPOINT}/{remittance_id}")

    assert listed.status_code == 200
    assert [item["remittance_id"] for item in listed.json()] == [remittance_id]
    assert one.status_code == 200
    body = one.json()
    assert body == listed.json()[0]
    assert body["quote_id"] == quote_id
    assert body["direction"] == "sent"
    assert body["counterparty_name"] == "Recip"
    assert body["counterparty_user_id"] == str(recipient_id)
    assert body["status"] == "pending"
    assert body["settled_at"] is None
    assert body["xrpl_tx_hash"] is None
    assert body["timeline_step"] == 2
    assert len(body["timeline"]) == 4
    assert body["timeline"][0]["title"] == "Quote accepted"
    assert Decimal(body["sender_amount"]) == Decimal("1000")
    assert body["sender_transaction_fee"] is not None
    assert body["exchange_rate_margin"] is not None


def test_the_recipient_reads_it_without_the_senders_fees(verified_client):
    client, sender = verified_client
    recipient_id, _quote_id, remittance_id = _confirmed_transfer(client, sender.id)
    _act_as(client, recipient_id)

    listed = client.get(ENDPOINT)
    one = client.get(f"{ENDPOINT}/{remittance_id}")

    assert [item["remittance_id"] for item in listed.json()] == [remittance_id]
    assert one.status_code == 200
    body = one.json()
    assert body["direction"] == "received"
    assert body["counterparty_name"] == "Verified"
    assert body["counterparty_user_id"] == str(sender.id)
    assert body["sender_amount"] is None
    assert body["sender_transaction_fee"] is None
    assert body["exchange_rate_margin"] is None
    assert body["receiver_payout_estimate"] is not None


def test_anyone_else_gets_a_404_and_an_empty_list(verified_client):
    client, sender = verified_client
    _recipient_id, _quote_id, remittance_id = _confirmed_transfer(client, sender.id)
    token = db.open_session()
    try:
        stranger = UserController().ensure_provisioned(
            "user_remit_stranger",
            lambda: "stranger@example.com",
            lambda: "Str",
        )
        stranger_id = stranger.id
    finally:
        db.close_session(token)
    _act_as(client, stranger_id)

    assert client.get(ENDPOINT).json() == []
    missing = client.get(f"{ENDPOINT}/{remittance_id}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Transfer not found"}


def test_an_unknown_transfer_is_a_404(verified_client):
    client, _sender = verified_client

    assert client.get(f"{ENDPOINT}/{uuid.uuid4()}").status_code == 404


def test_the_list_is_newest_first_and_limited(verified_client):
    client, sender = verified_client
    recipient_id = _seed(client, sender.id)
    first = _create_quote(client, recipient_id, amount="100")
    second = _create_quote(client, recipient_id, amount="200")
    client.post(ENDPOINT, json={"quote_id": first})
    client.post(ENDPOINT, json={"quote_id": second})

    everything = client.get(ENDPOINT).json()
    latest = client.get(ENDPOINT, params={"limit": 1}).json()

    assert [item["quote_id"] for item in everything] == [second, first]
    assert [item["quote_id"] for item in latest] == [second]


def test_status_and_hash_follow_a_confirmed_settlement(
    verified_client, worker_on_app_db
):
    client, sender = verified_client
    recipient_id, quote_id, remittance_id = _confirmed_transfer(client, sender.id)

    tasks.confirm_treasury_burn(quote_id, "A1B2C3D4E5F6")

    for reader in (sender.id, recipient_id):
        _act_as(client, reader)
        body = client.get(f"{ENDPOINT}/{remittance_id}").json()
        assert body["status"] == "confirmed"
        assert body["xrpl_tx_hash"] == "A1B2C3D4E5F6"
        assert body["settled_at"] is not None


def test_status_follows_a_failed_settlement_without_a_hash(
    verified_client, worker_on_app_db
):
    client, sender = verified_client
    _recipient_id, quote_id, remittance_id = _confirmed_transfer(client, sender.id)

    tasks.confirm_treasury_burn(quote_id, None, "tecPATH_DRY")

    body = client.get(f"{ENDPOINT}/{remittance_id}").json()
    assert body["status"] == "failed"
    assert body["xrpl_tx_hash"] is None
    assert body["settled_at"] is None
