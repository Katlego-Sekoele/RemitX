import uuid

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, TYPE_PLATFORM_FIAT, Account
from remitx_api.services import deposit_service

ENDPOINT = "/admin/deposits/process"


def _seed_bank_account() -> Account:
    admin = UserController().ensure_provisioned(
        "user_admin_seed", lambda: "admin@example.com", lambda: "Admin"
    )
    account = Account(
        user_id=admin.id,
        type=TYPE_PLATFORM_FIAT,
        account_currency=CURRENCY_ZAR,
        label=deposit_service.REMITX_SA_BANK_ACCOUNT_LABEL,
    )
    db.session.add(account)
    db.session.commit()
    return account


def test_non_admin_is_rejected(client):
    response = client.post(ENDPOINT, json={"rows": []})

    assert response.status_code == 403


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(ENDPOINT, json={"rows": []})

    assert response.status_code == 401


def test_admin_confirms_a_matching_row(admin_client):
    token = db.open_session()
    try:
        _seed_bank_account()
        user = UserController().ensure_provisioned(
            "user_dep_route", lambda: "dep@example.com", lambda: "Dep"
        )
        zar_reference = f"{user.base_reference}-zar"
    finally:
        db.close_session(token)

    response = admin_client.post(
        ENDPOINT,
        json={
            "rows": [
                {"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"}
            ]
        },
    )

    assert response.status_code == 200
    [result] = response.json()
    assert result["status"] == "confirmed"
    assert result["user_id"] == str(user.id)
    assert result["amount"] == "500.00000000"
    assert result["currency"] == CURRENCY_ZAR


def test_admin_leaves_an_unmatched_row_pending(admin_client):
    token = db.open_session()
    try:
        _seed_bank_account()
    finally:
        db.close_session(token)

    response = admin_client.post(
        ENDPOINT,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-10"}
            ]
        },
    )

    assert response.status_code == 200
    [result] = response.json()
    assert result["status"] == "pending"
    assert result["user_id"] is None


def test_pending_endpoint_lists_only_unmatched_deposits(admin_client):
    token = db.open_session()
    try:
        _seed_bank_account()
    finally:
        db.close_session(token)

    admin_client.post(
        ENDPOINT,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-10"}
            ]
        },
    )

    response = admin_client.get("/admin/deposits/pending")

    assert response.status_code == 200
    [result] = response.json()
    assert result["reference"] == "remitx deposit"
    assert result["amount"] == "80.00000000"
    assert result["created_at"].endswith("+00:00")


def test_admin_approves_a_pending_deposit(admin_client):
    token = db.open_session()
    try:
        _seed_bank_account()
        user = UserController().ensure_provisioned(
            "user_approve_route", lambda: "approve@example.com", lambda: "App"
        )
        user_id = str(user.id)
    finally:
        db.close_session(token)

    admin_client.post(
        ENDPOINT,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-10"}
            ]
        },
    )
    [pending] = admin_client.get("/admin/deposits/pending").json()

    response = admin_client.post(
        f"/admin/deposits/{pending['deposit_id']}/approve",
        json={"user_id": user_id},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "confirmed"
    assert result["user_id"] == user_id
    assert admin_client.get("/admin/deposits/pending").json() == []


def test_approving_an_unknown_deposit_is_a_400(admin_client):
    token = db.open_session()
    try:
        user = UserController().ensure_provisioned(
            "user_approve_missing", lambda: "missing@example.com", lambda: "Miss"
        )
        user_id = str(user.id)
    finally:
        db.close_session(token)

    response = admin_client.post(
        f"/admin/deposits/{uuid.uuid4()}/approve",
        json={"user_id": user_id},
    )

    assert response.status_code == 400
