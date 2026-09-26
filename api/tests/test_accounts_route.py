import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.account_controller import describe_leg
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    PAYOUT_CURRENCIES,
    TYPE_PLATFORM_REVENUE,
    Account,
    create_account_reference,
)
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.user import User, short_display_name
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import deposit_service, remittance_service
from remitx_worker import db as worker_db
from remitx_worker.tasks import confirm_treasury_burn
from sqlalchemy.orm import sessionmaker
from tests.kyc_helpers import seed_kyc_reference_data
from tests.platform_account_helpers import seed_platform_accounts

ACCOUNTS = "/accounts"
HISTORY = "/accounts-history"
LOOKUP = "/beneficiaries/lookup-by-reference"


def test_accounts_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.get(ACCOUNTS)

    assert response.status_code == 401


def test_open_account_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(ACCOUNTS, json={"currency": "USD"})

    assert response.status_code == 401


def test_open_account_requires_kyc_verification(client):
    token = db.open_session()
    try:
        seed_kyc_reference_data()
    finally:
        db.close_session(token)

    response = client.post(ACCOUNTS, json={"currency": "USD"})

    assert response.status_code == 403
    assert "verified" in response.json()["detail"].lower()


@pytest.mark.parametrize("currency", PAYOUT_CURRENCIES)
def test_open_account_creates_each_payout_currency(verified_client, currency):
    client, sender = verified_client
    if currency == CURRENCY_ZAR:
        pytest.skip("ZAR is created at sign-up")

    response = client.post(ACCOUNTS, json={"currency": currency})

    assert response.status_code == 201
    body = response.json()
    assert body["currency"] == currency
    assert body["kind"] == "fiat"
    assert body["balance"] == "0.00"
    assert body["available_balance"] == "0.00"
    assert body["reference"] == create_account_reference(
        sender.base_reference, currency
    )


def test_open_account_duplicate_currency_is_409(verified_client):
    client, sender = verified_client

    first = client.post(ACCOUNTS, json={"currency": "USD"})
    assert first.status_code == 201

    second = client.post(ACCOUNTS, json={"currency": "USD"})

    assert second.status_code == 409
    assert "already" in second.json()["detail"].lower()


def test_open_account_rejects_settlement_token(verified_client):
    client, _sender = verified_client
    token_name = TestConfig().UCTUSD_TOKEN_NAME

    response = client.post(ACCOUNTS, json={"currency": token_name})

    assert response.status_code == 422


def test_open_account_rejects_unsupported_currency(verified_client):
    client, _sender = verified_client

    response = client.post(ACCOUNTS, json={"currency": "EUR"})

    assert response.status_code == 422


def test_open_account_reference_works_in_beneficiary_lookup(verified_client):
    client, sender = verified_client
    other_id = _provision_other_user("open_account_lookup")

    opened = client.post(ACCOUNTS, json={"currency": "NAD"})
    assert opened.status_code == 201
    reference = opened.json()["reference"]

    _sign_in_as(client, User(id=other_id, base_reference="other1"))
    lookup = client.get(LOOKUP, params={"account_reference": reference})

    assert lookup.status_code == 200
    assert lookup.json()["account_currency"] == "NAD"
    assert "NAD" in lookup.json()["payout_currencies"]


def _provision_other_user(clerk_id: str) -> uuid.UUID:
    token = db.open_session()
    try:
        other = UserController().ensure_provisioned(
            clerk_id,
            lambda: f"{clerk_id}@example.com",
            lambda: "Other",
        )
        return other.id
    finally:
        db.close_session(token)


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


def test_history_query_runs_inside_the_callers_row_security_context(
    verified_client, monkeypatch
):
    """The history query sees the stamp ``rls.py`` puts on the request.

    ``create_customer_router`` binds the caller before the handler runs.
    On Postgres the cursor hook copies that onto ``app.current_user_id``
    and ``app.is_admin_route``, which the ledger policies read. The query
    predicates are the same rule for SQLite, where that hook does nothing.
    """
    client, sender = verified_client
    seen = {}
    real = TransactionRepository.list_account_transactions

    def spy(self, account_id, limit=None, before=None, user_id=None):
        seen["user_id"] = db.session.info.get("row_security_current_user_id")
        seen["is_admin_route"] = db.session.info.get("row_security_is_admin_route")
        return real(self, account_id, limit=limit, before=before, user_id=user_id)

    monkeypatch.setattr(TransactionRepository, "list_account_transactions", spy)
    account_id = client.get(ACCOUNTS).json()[0]["account_id"]

    response = client.get(HISTORY, params={"account_id": account_id})

    assert response.status_code == 200
    assert seen == {"user_id": str(sender.id), "is_admin_route": False}


def _send_remittance(client, sender, monkeypatch, funded="1000", amount="1000"):
    """Seed the platform accounts and rates, fund the sender's ZAR account
    with `funded`, and confirm a ZAR -> ZWL send of `amount` to a new
    recipient, Recip Moyo. Settlement is left queued. Returns the quote's
    JSON, the confirmed remittance's JSON, and the recipient as a transient
    `User` a test can sign in as."""
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

        seed_platform_accounts()

        recipient = UserController().ensure_provisioned(
            "user_accounts_route_recipient",
            lambda: "accounts-route-recipient@example.com",
            lambda: "Recip",
        )
        recipient.last_name = "moyo"
        AccountRepository().get_or_create_user_account(
            recipient.id, recipient.base_reference, CURRENCY_ZWL
        )

        sender_zar = AccountRepository().get_user_account(sender.id, CURRENCY_ZAR)
        AccountRepository().increase_balance(sender_zar.account_id, Decimal(funded))
        db.session.commit()
        recipient_id = recipient.id
        recipient_reference = recipient.base_reference
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
    recipient = User(id=recipient_id, base_reference=recipient_reference)
    return quote_response.json(), confirm_response.json(), recipient


def test_a_remittance_shows_up_correctly_on_both_sides(verified_client, monkeypatch):
    client, sender = verified_client
    quote, _remittance, _recipient = _send_remittance(client, sender, monkeypatch)

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


BURN_HASH = "A1B2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4E5F60718293A4B5C6D7E9F0E"


def _settle(quote_id: str, tx_hash: str | None = BURN_HASH) -> None:
    """Run the worker's final settlement step against the test database, as
    a worker consuming `confirm_treasury_burn` would."""
    worker_db.configure(sessionmaker(bind=db.engine))
    try:
        confirm_treasury_burn(quote_id, tx_hash, None if tx_hash else "boom")
    finally:
        worker_db.configure(None)


def _history(client, currency: str, **params) -> list[dict]:
    accounts = {a["currency"]: a for a in client.get(ACCOUNTS).json()}
    response = client.get(
        HISTORY,
        params={"account_id": accounts[currency]["account_id"], **params},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _sign_in_as(client, user: User) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: user


def _seed_bank_account() -> None:
    token = db.open_session()
    try:
        seed_platform_accounts()
    finally:
        db.close_session(token)


def _deposit(reference: str, *lines: tuple[str, str]) -> None:
    token = db.open_session()
    try:
        deposit_service.process_deposits(
            [
                {
                    "reference": reference,
                    "amount": amount,
                    "currency": "ZAR",
                    "date": date,
                }
                for amount, date in lines
            ]
        )
    finally:
        db.close_session(token)


def test_history_describes_a_deposit(verified_client):
    client, sender = verified_client
    _seed_bank_account()
    _deposit(f"{sender.base_reference}-zar", ("250.5", "2026-09-20"))

    (leg,) = _history(client, CURRENCY_ZAR)

    assert leg["description"] == "Deposit"
    assert leg["direction"] == "in"
    assert leg["amount"] == "250.50"
    assert leg["status"] == "confirmed"
    assert leg["counterparty_name"] is None
    assert leg["remittance_id"] is None
    assert leg["xrpl_tx_hash"] is None


def test_history_describes_a_sent_transfer_while_it_is_queued(
    verified_client, monkeypatch
):
    client, sender = verified_client
    _quote, remittance, _recipient = _send_remittance(client, sender, monkeypatch)

    zar_legs = _history(client, CURRENCY_ZAR)
    assert {leg["description"] for leg in zar_legs} == {
        "Transfer fee",
        "Sent to Recip M.",
    }
    token_legs = {leg["direction"]: leg for leg in _history(client, CURRENCY_TOKEN)}
    assert token_legs["in"]["description"] == "Converted from ZAR"
    assert token_legs["out"]["description"] == "Sent to Recip M."

    for leg in [*zar_legs, *token_legs.values()]:
        assert leg["counterparty_name"] == "Recip M."
        assert leg["remittance_id"] == remittance["remittance_id"]
        assert leg["status"] == "pending"
        # No hash until the burn has confirmed on-chain.
        assert leg["xrpl_tx_hash"] is None


def test_a_settled_transfer_carries_the_burn_hash_on_every_senders_leg(
    verified_client, monkeypatch
):
    client, sender = verified_client
    quote, _remittance, _recipient = _send_remittance(client, sender, monkeypatch)

    _settle(quote["quote_id"])

    legs = [*_history(client, CURRENCY_ZAR), *_history(client, CURRENCY_TOKEN)]
    assert len(legs) == 4
    for leg in legs:
        assert leg["status"] == "confirmed"
        assert leg["xrpl_tx_hash"] == BURN_HASH


def test_a_failed_transfer_has_no_hash(verified_client, monkeypatch):
    client, sender = verified_client
    quote, _remittance, _recipient = _send_remittance(client, sender, monkeypatch)

    _settle(quote["quote_id"], tx_hash=None)

    for leg in _history(client, CURRENCY_ZAR):
        assert leg["status"] == "failed"
        assert leg["xrpl_tx_hash"] is None


def test_history_describes_a_received_transfer(verified_client, monkeypatch):
    client, sender = verified_client
    quote, remittance, recipient = _send_remittance(client, sender, monkeypatch)
    _settle(quote["quote_id"])

    _sign_in_as(client, recipient)

    (payout,) = _history(client, CURRENCY_ZWL)
    assert payout["description"] == "Received from Verified"
    assert payout["direction"] == "in"
    assert Decimal(payout["amount"]) == Decimal(quote["receiver_amount"])
    assert payout["currency"] == CURRENCY_ZWL

    # The recipient's RLUSD wallet: the brief's incoming and cash-out rows.
    wallet = {leg["direction"]: leg for leg in _history(client, CURRENCY_TOKEN)}
    assert wallet["in"]["description"] == "Received from Verified"
    assert wallet["out"]["description"] == "Converted to ZWL"

    for leg in [payout, *wallet.values()]:
        assert leg["counterparty_name"] == "Verified"
        assert leg["remittance_id"] == remittance["remittance_id"]
        assert leg["xrpl_tx_hash"] == BURN_HASH
    # Nothing of the sender's fee reaches the recipient's history.
    assert all(leg["description"] != "Transfer fee" for leg in wallet.values())


def test_history_pages_newest_first_with_limit_and_before(verified_client):
    client, sender = verified_client
    _seed_bank_account()
    _deposit(
        f"{sender.base_reference}-zar",
        ("10", "2026-09-18"),
        ("20", "2026-09-19"),
        ("30", "2026-09-20"),
    )

    first = _history(client, CURRENCY_ZAR, limit=2)
    assert [leg["amount"] for leg in first] == ["30.00", "20.00"]

    rest = _history(client, CURRENCY_ZAR, limit=2, before=first[-1]["created_at"])
    assert [leg["amount"] for leg in rest] == ["10.00"]

    assert _history(client, CURRENCY_ZAR, before=rest[-1]["created_at"]) == []


def test_history_defaults_to_pages_of_fifty(verified_client):
    client, sender = verified_client
    _seed_bank_account()
    _deposit(
        f"{sender.base_reference}-zar",
        *[("1", f"2026-08-{day:02d}") for day in range(1, 29)],
        *[("1", f"2026-09-{day:02d}") for day in range(1, 29)],
    )

    assert len(_history(client, CURRENCY_ZAR)) == 50


def test_history_limit_out_of_range_is_a_422(verified_client):
    client, _sender = verified_client
    zar = {a["currency"]: a for a in client.get(ACCOUNTS).json()}[CURRENCY_ZAR]

    for limit in (0, 201):
        response = client.get(
            HISTORY, params={"account_id": zar["account_id"], "limit": limit}
        )
        assert response.status_code == 422


def test_history_refuses_a_platform_account(verified_client):
    client, _ = verified_client
    token = db.open_session()
    try:
        platform = Account(
            user_id=None,
            type=TYPE_PLATFORM_REVENUE,
            account_currency=CURRENCY_ZAR,
            label="RemitX SA Fee Revenue",
        )
        db.session.add(platform)
        db.session.commit()
        platform_id = platform.account_id
    finally:
        db.close_session(token)

    response = client.get(HISTORY, params={"account_id": str(platform_id)})

    assert response.status_code == 400


def test_short_display_name():
    assert short_display_name("Tendai", "moyo") == "Tendai M."
    assert short_display_name("Tendai", None) == "Tendai"
    assert short_display_name("Tendai", "  ") == "Tendai"
    assert short_display_name(None, "Moyo") is None
    assert short_display_name("  ", None) is None


def test_an_unknown_leg_type_off_a_transfer_still_reads():
    assert describe_leg("treasury_funding", "in", "fiat", None) == ("Treasury funding")
