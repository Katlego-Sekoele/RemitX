import hashlib
import hmac
import json
import time
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from remitx_api.extensions import db
from remitx_api.models.orm.transaction import STATUS_CONFIRMED
from remitx_api.repositories.account_repository import AccountRepository
from tests.platform_account_helpers import seed_platform_accounts


def _seed_platform():
    token = db.open_session()
    try:
        seed_platform_accounts()
    finally:
        db.close_session(token)


def _zar_balance(user_id):
    token = db.open_session()
    try:
        return AccountRepository().get_user_account(user_id, "ZAR").account_balance
    finally:
        db.close_session(token)


def _enable_trustmebank(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUSTMEBANK", "true")
    monkeypatch.setenv("TRUSTMEBANK_WEBHOOK_SECRET", "whsec_test")


def _sign(body: bytes, secret: str = "whsec_test") -> str:
    timestamp = int(time.time())
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.fixture
def trustmebank_client(monkeypatch):
    _enable_trustmebank(monkeypatch)
    mock = MagicMock()
    mock.authorize_url.side_effect = (
        lambda *, state, redirect_uri, scope: (
            f"https://bank.example/oauth?state={state}"
        )
    )
    mock.exchange_code.return_value = MagicMock(
        access_token="tmbat_test",
        refresh_token="tmbrt_test",
        expires_in=3600,
        scope="accounts payments",
        consent_id="consent_test",
    )
    mock.get_me.return_value = {
        "customer_id": "cust_test",
        "full_name": "Alice Ndlovu",
    }
    mock.create_payment.return_value = MagicMock(
        payment_id="pay_test_1",
        status="AWAITING_AUTHORISATION",
        amount="100.00",
        currency="ZAR",
        reference="RX-TEST",
        authorisation_url="https://bank.example/authorise",
    )
    mock.get_payment.return_value = {
        "payment_id": "pay_test_1",
        "status": "COMPLETED",
    }
    monkeypatch.setattr(
        "remitx_api.services.trustmebank_service.TrustMeBankClient",
        lambda config=None: mock,
    )
    return mock


def test_status_disabled(client):
    response = client.get("/trustmebank/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_status_enabled(client, monkeypatch):
    _enable_trustmebank(monkeypatch)
    response = client.get("/trustmebank/status")
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


def test_oauth_and_deposit_confirmed_once(
    verified_client, trustmebank_client, monkeypatch
):
    client, user = verified_client
    _seed_platform()

    connect = client.post("/trustmebank/connect")
    assert connect.status_code == 200
    authorize_url = connect.json()["authorize_url"]
    state = authorize_url.split("state=")[-1].split("&")[0]

    callback = client.post(
        "/trustmebank/oauth/callback",
        json={"code": "code_test", "state": state},
    )
    assert callback.status_code == 200
    assert callback.json()["customer_name"] == "Alice Ndlovu"

    start = client.post(
        "/trustmebank/deposits",
        json={"amount": "100.00", "debtor_account_id": "acc_test"},
    )
    assert start.status_code == 200
    payment_id = start.json()["payment_id"]

    before = _zar_balance(user.id)

    body = json.dumps(
        {
            "id": "evt_1",
            "event": "payment.completed",
            "data": {
                "payment_id": payment_id,
                "status": "COMPLETED",
                "amount": "100.00",
            },
        }
    ).encode()
    webhook = client.post(
        "/webhooks/trustmebank",
        content=body,
        headers={"X-TrustMeBank-Signature": _sign(body)},
    )
    assert webhook.status_code == 204

    after = _zar_balance(user.id)
    assert after == before + Decimal("100.00")

    replay = client.post(
        "/webhooks/trustmebank",
        content=body,
        headers={"X-TrustMeBank-Signature": _sign(body)},
    )
    assert replay.status_code == 204
    assert (
        _zar_balance(user.id) == after
    )


def test_sync_poll_confirms_deposit(verified_client, trustmebank_client, monkeypatch):
    client, user = verified_client
    _seed_platform()

    connect = client.post("/trustmebank/connect")
    state = connect.json()["authorize_url"].split("state=")[-1].split("&")[0]
    client.post(
        "/trustmebank/oauth/callback",
        json={"code": "code_test", "state": state},
    )
    start = client.post(
        "/trustmebank/deposits",
        json={"amount": "50.00", "debtor_account_id": "acc_test"},
    )
    payment_id = start.json()["payment_id"]
    before = _zar_balance(user.id)

    sync = client.post(f"/trustmebank/deposits/{payment_id}/sync")
    assert sync.status_code == 200
    assert sync.json()["status"] == STATUS_CONFIRMED
    after = _zar_balance(user.id)
    assert after == before + Decimal("50.00")


def test_routes_hidden_when_disabled(verified_client):
    client, _user = verified_client
    assert client.post("/trustmebank/connect").status_code == 404
