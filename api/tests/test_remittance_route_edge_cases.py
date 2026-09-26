"""Hostile or malformed input at the quote and remittance endpoints.

The frontend validates amounts first, but the API may not rely on that
(Transaction_Flow_Context.md §7, "Input validation happens on both
sides"). Every bad amount must be refused with a 4xx, never a 500, and
never produce a quote.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, CURRENCY_ZWL
from remitx_api.models.orm.exchange_rate import ExchangeRate
from remitx_api.models.orm.quote import Quote
from remitx_api.repositories.account_repository import AccountRepository
from sqlalchemy import func, select


def _seed(client, sender):
    """Rates, a funded sender and a ZWL beneficiary. Returns its id."""
    token = db.open_session()
    try:
        now = datetime.now(UTC)
        db.session.add_all(
            [
                ExchangeRate(
                    base_currency=base,
                    quote_currency=quote,
                    rate=Decimal(rate),
                    fetched_at=now,
                    valid_until=now + timedelta(hours=1),
                )
                for base, quote, rate in (
                    ("USD", "ZAR", "18.50"),
                    ("ZAR", "ZWL", "16.22"),
                )
            ]
        )
        recipient = UserController().ensure_provisioned(
            "user_edge_recipient", lambda: "edge-recipient@example.com", lambda: "R"
        )
        AccountRepository().get_or_create_user_account(
            recipient.id, recipient.base_reference, CURRENCY_ZWL
        )
        sender_zar = AccountRepository().get_user_account(sender.id, CURRENCY_ZAR)
        AccountRepository().increase_balance(sender_zar.account_id, Decimal("1000"))
        db.session.commit()
        recipient_id = recipient.id
    finally:
        db.close_session(token)

    response = client.post(
        "/beneficiaries/create-beneficiary",
        json={
            "linked_user_id": str(recipient_id),
            "payout_currency": "ZWL",
            "relationship": "sibling",
        },
    )
    assert response.status_code == 200
    return response.json()["beneficiary_id"]


def _quote_count():
    token = db.open_session()
    try:
        return db.session.scalar(select(func.count()).select_from(Quote))
    finally:
        db.close_session(token)


BAD_AMOUNTS = [
    "-100",
    "0",
    "0.001",  # rounds to 0.00
    "NaN",
    "Infinity",
    "-Infinity",
    "1e30",  # beyond Decimal's 28-digit precision once quantized
    "not-a-number",
]


@pytest.mark.parametrize("amount", BAD_AMOUNTS)
def test_create_quote_refuses_bad_amounts_with_a_4xx(verified_client, amount):
    client, sender = verified_client
    beneficiary_id = _seed(client, sender)

    response = client.post(
        "/quotes/create-quote",
        json={
            "beneficiary_id": beneficiary_id,
            "sender_amount": amount,
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )

    assert 400 <= response.status_code < 500, response.text
    assert _quote_count() == 0


@pytest.mark.parametrize("amount", BAD_AMOUNTS)
def test_preview_quote_refuses_bad_amounts_with_a_4xx(verified_client, amount):
    client, sender = verified_client
    _seed(client, sender)

    response = client.post(
        "/quotes/preview-quote",
        json={
            "sender_amount": amount,
            "sender_currency": "ZAR",
            "receiver_payout_currency": "ZWL",
        },
    )

    assert 400 <= response.status_code < 500, response.text


def test_confirm_with_a_malformed_quote_id_is_a_422(verified_client):
    client, _sender = verified_client

    response = client.post("/remittances", json={"quote_id": "not-a-uuid"})

    assert response.status_code == 422


def test_a_sender_cannot_add_themselves_as_a_beneficiary(verified_client):
    """Sending to yourself would round-trip money through FX and the
    treasury for no reason. The by-reference lookup already refuses the
    caller's own account (OwnAccountReferenceError); adding by user id
    should too."""
    client, sender = verified_client
    token = db.open_session()
    try:
        AccountRepository().get_or_create_user_account(
            sender.id, sender.base_reference, CURRENCY_ZWL
        )
        db.session.commit()
    finally:
        db.close_session(token)

    response = client.post(
        "/beneficiaries/create-beneficiary",
        json={
            "linked_user_id": str(sender.id),
            "payout_currency": "ZWL",
            "relationship": "self",
        },
    )

    assert 400 <= response.status_code < 500, response.text
