"""The customer dashboard: limits, activity, in-flight transfers, beneficiaries."""

from datetime import UTC, datetime
from decimal import Decimal

import time_machine
from remitx_api.auth.dependencies import get_current_user
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, CURRENCY_ZWL
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
)
from remitx_api.models.orm.user import User
from remitx_api.services.send_limits import SAST
from tests.kyc_helpers import make_user
from tests.send_helpers import record_transfer

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
    assert all(day["payout_received"] == "0.00" for day in body["activity"])


def test_dashboard_counts_sends_and_leaves_out_failures(verified_client):
    client, sender = verified_client
    token = db.open_session()
    try:
        beneficiary = make_user("dash-beneficiary")
        beneficiary.first_name = "Amahle"
        beneficiary.last_name = "Dlamini"
        record_transfer(
            sender,
            beneficiary,
            sender_amount=Decimal("1000"),
            token_amount=Decimal("50"),
            status=STATUS_CONFIRMED,
        )
        record_transfer(
            sender,
            beneficiary,
            sender_amount=Decimal("100"),
            token_amount=Decimal("5"),
            status=STATUS_PENDING,
        )
        record_transfer(
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
    assert day["payout_received"] == "0.00"
    assert body["beneficiaries"] == [{"name": "Amahle D.", "zar_sent": "1100.00"}]
    assert len(body["in_flight"]) == 1
    inflight = body["in_flight"][0]
    assert inflight["direction"] == "sent"
    assert inflight["status"] == "pending"
    assert inflight["counterparty_name"] == "Amahle D."
    assert inflight["amount"] == "100.00"
    assert inflight["currency"] == CURRENCY_ZAR


def test_dashboard_limits_count_the_south_african_day(verified_client):
    """At 01:00 SAST, a send at 23:30 the night before is yesterday's, though
    both are the same UTC day. The ring shows what the limit check counts."""
    client, sender = verified_client
    with time_machine.travel(datetime(2025, 6, 15, 1, tzinfo=SAST), tick=False):
        token = db.open_session()
        try:
            record_transfer(
                sender,
                make_user("dash-late-beneficiary"),
                sender_amount=Decimal("3000"),
                at=datetime(2025, 6, 14, 23, 30, tzinfo=SAST),
            )
            db.session.commit()
        finally:
            db.close_session(token)

        limits = client.get(DASHBOARD).json()["limits"]

    assert limits["daily_sent_zar"] == "0.00"
    assert limits["monthly_sent_zar"] == "3000.00"


def test_dashboard_received_activity_uses_payout_not_settlement_token(
    verified_client,
):
    """Recipients see what lands in their payout currency, not RLUSD on the
    settlement leg."""
    client, sender = verified_client
    token = db.open_session()
    try:
        recipient = make_user("dash-recipient")
        record_transfer(
            sender,
            recipient,
            sender_amount=Decimal("1000"),
            token_amount=Decimal("52.43"),
            receiver_amount=Decimal("1354.37"),
            receiver_currency=CURRENCY_ZWL,
            status=STATUS_CONFIRMED,
        )
        record_transfer(
            sender,
            recipient,
            sender_amount=Decimal("100"),
            token_amount=Decimal("5.24"),
            receiver_amount=Decimal("135.44"),
            receiver_currency=CURRENCY_ZWL,
            status=STATUS_PENDING,
        )
        db.session.commit()
        recipient_id = recipient.id
    finally:
        db.close_session(token)

    client.app.dependency_overrides[get_current_user] = lambda: User(id=recipient_id)
    body = client.get(DASHBOARD).json()
    today = datetime.now(UTC).date().isoformat()
    day = next(row for row in body["activity"] if row["day"] == today)

    assert day["payout_received"] == "1489.81"
    assert day["zar_sent"] == "0.00"
    inflight = next(
        row for row in body["in_flight"] if row["direction"] == "received"
    )
    assert inflight["amount"] == "135.44"
    assert inflight["currency"] == CURRENCY_ZWL
