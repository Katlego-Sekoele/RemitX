import uuid
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.user import User
from remitx_api.services import bank_account_service
from tests.rbac_helpers import grant_permissions, grant_role, seed_rbac_catalogue

BANK_ACCOUNTS = "/bank-accounts"
PENDING = "/admin/bank-accounts/pending"


def _verify_path(bank_account_id) -> str:
    return f"/admin/bank-accounts/{bank_account_id}/verify"


def _reject_path(bank_account_id) -> str:
    return f"/admin/bank-accounts/{bank_account_id}/reject"


def _payload(**overrides) -> dict:
    payload = {
        "account_holder_name": "Test User",
        "bank_name": "First National Bank",
        "account_number": "1234567890",
        "currency": "ZAR",
        "branch_code": "250655",
        "country": "ZA",
    }
    payload.update(overrides)
    return payload


@dataclass
class Env:
    """One app, one database, two real persisted callers — a customer and a
    `payout_operator` admin — sharing it. Not two separate
    `create_app(TestConfig)` clients: each call re-runs `db.init(...)` on the
    global `db` singleton (remitx_api/app.py), so a second app would silently
    swap out the database the first client's requests were using.
    """

    client: TestClient
    app: FastAPI
    customer: User
    admin: User

    def as_customer(self) -> None:
        self.app.dependency_overrides[get_current_user] = lambda: self.customer

    def as_admin(self) -> None:
        self.app.dependency_overrides[get_current_user] = lambda: self.admin


@pytest.fixture
def env():
    app = create_app(TestConfig)
    with TestClient(app) as client:
        token = db.open_session()
        try:
            customer = UserController().ensure_provisioned(
                "user_bank_customer",
                lambda: "bank-customer@example.com",
                lambda: "Cust",
            )
            seed_rbac_catalogue()
            admin = UserController().ensure_provisioned(
                "user_bank_admin", lambda: "bank-admin@example.com", lambda: "Admin"
            )
            grant_role(admin.id, "payout_operator")

            customer_user = User(id=customer.id, base_reference=customer.base_reference)
            admin_user = User(id=admin.id)
        finally:
            db.close_session(token)

        testenv = Env(client=client, app=app, customer=customer_user, admin=admin_user)
        testenv.as_customer()
        yield testenv


def test_anonymous_caller_is_rejected(anonymous_client):
    assert anonymous_client.post(BANK_ACCOUNTS, json=_payload()).status_code == 401
    assert anonymous_client.get(BANK_ACCOUNTS).status_code == 401


def test_adding_a_bank_account_starts_pending_verification(env):
    response = env.client.post(BANK_ACCOUNTS, json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending_verification"
    assert body["account_number"] == "****7890"


def test_listing_masks_the_account_number_but_admin_sees_it_in_full(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    list_response = env.client.get(BANK_ACCOUNTS)
    assert list_response.json()[0]["account_number"] == "****7890"

    env.as_admin()
    pending_response = env.client.get(PENDING)
    assert pending_response.json()[0]["account_number"] == "1234567890"

    verify_response = env.client.post(_verify_path(account["bank_account_id"]), json={})
    assert verify_response.json()["account_number"] == "1234567890"


def test_listing_only_returns_the_caller_own_bank_accounts(env):
    env.client.post(BANK_ACCOUNTS, json=_payload())

    token = db.open_session()
    try:
        other = UserController().ensure_provisioned(
            "user_other_bank", lambda: "other-bank@example.com", lambda: "Other"
        )
        bank_account_service.add_bank_account(
            other.id, "Someone Else", "Standard Bank", "999", "ZAR"
        )
    finally:
        db.close_session(token)

    response = env.client.get(BANK_ACCOUNTS)

    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) == 1
    assert accounts[0]["account_holder_name"] == "Test User"


def test_listing_can_be_filtered_by_currency_regardless_of_status(env):
    zar_account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()
    env.client.post(BANK_ACCOUNTS, json=_payload(currency="USD"))

    response = env.client.get(f"{BANK_ACCOUNTS}?currency=ZAR")

    assert response.status_code == 200
    accounts = response.json()
    assert len(accounts) == 1
    assert accounts[0]["bank_account_id"] == zar_account["bank_account_id"]
    assert accounts[0]["status"] == "pending_verification"


def test_withdrawable_only_returns_verified_accounts_in_that_currency(env):
    zar_account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()
    env.client.post(BANK_ACCOUNTS, json=_payload(currency="USD"))

    # Still pending_verification: neither should be offered yet.
    response = env.client.get(f"{BANK_ACCOUNTS}/withdrawable?currency=ZAR")
    assert response.status_code == 200
    assert response.json() == []

    env.as_admin()
    env.client.post(_verify_path(zar_account["bank_account_id"]), json={})
    env.as_customer()

    zar_response = env.client.get(f"{BANK_ACCOUNTS}/withdrawable?currency=ZAR")
    assert zar_response.status_code == 200
    accounts = zar_response.json()
    assert len(accounts) == 1
    assert accounts[0]["bank_account_id"] == zar_account["bank_account_id"]
    assert accounts[0]["status"] == "verified"

    usd_response = env.client.get(f"{BANK_ACCOUNTS}/withdrawable?currency=USD")
    assert usd_response.json() == []


def test_admin_without_cashout_permission_is_rejected(client):
    assert client.get(PENDING).status_code == 403


def test_cashout_read_alone_cannot_verify(env):
    """`cashout:read` is the admin router's baseline; verifying escalates to
    `cashout:approve` on top of it — a read-only viewer, unlike
    `env.admin` (full `payout_operator`), must not be able to do both."""
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    token = db.open_session()
    try:
        viewer = UserController().ensure_provisioned(
            "user_bank_viewer", lambda: "bank-viewer@example.com", lambda: "Viewer"
        )
        grant_permissions(
            viewer.id, PermissionCode.CASHOUT_READ, role_name="viewer_only"
        )
        viewer_id = viewer.id
    finally:
        db.close_session(token)

    env.app.dependency_overrides[get_current_user] = lambda: User(id=viewer_id)
    assert env.client.get(PENDING).status_code == 200
    blocked = env.client.post(_verify_path(account["bank_account_id"]), json={})
    assert blocked.status_code == 403


def test_payout_operator_verifies_a_pending_bank_account(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    env.as_admin()
    response = env.client.post(_verify_path(account["bank_account_id"]), json={})

    assert response.status_code == 200
    assert response.json()["status"] == "verified"
    assert env.client.get(PENDING).json() == []


def test_payout_operator_rejects_a_pending_bank_account(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    env.as_admin()
    response = env.client.post(
        _reject_path(account["bank_account_id"]),
        json={"reason": "Account number does not match holder name"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "Account number does not match holder name"


def test_verifying_an_unknown_bank_account_is_a_400(env):
    env.as_admin()
    response = env.client.post(_verify_path(uuid.uuid4()), json={})

    assert response.status_code == 400


def test_verifying_twice_is_a_400(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    env.as_admin()
    env.client.post(_verify_path(account["bank_account_id"]), json={})
    response = env.client.post(_verify_path(account["bank_account_id"]), json={})

    assert response.status_code == 400


def test_rejecting_an_unknown_bank_account_is_a_400(env):
    env.as_admin()
    response = env.client.post(_reject_path(uuid.uuid4()), json={"reason": "x"})

    assert response.status_code == 400


@pytest.mark.parametrize(
    "first, second", [("verify", "reject"), ("reject", "verify"), ("reject", "reject")]
)
def test_a_decided_bank_account_cannot_be_decided_again(env, first, second):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()
    paths = {"verify": _verify_path, "reject": _reject_path}

    env.as_admin()
    first_response = env.client.post(
        paths[first](account["bank_account_id"]), json={"reason": "r"}
    )
    assert first_response.status_code == 200
    second_response = env.client.post(
        paths[second](account["bank_account_id"]), json={"reason": "r"}
    )

    assert second_response.status_code == 400
    assert second_response.json()["detail"]  # the first decision stands
    env.as_customer()
    assert env.client.get(BANK_ACCOUNTS).json()[0]["status"] == (
        "verified" if first == "verify" else "rejected"
    )


def test_rejecting_without_a_reason_is_a_422(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    env.as_admin()
    response = env.client.post(_reject_path(account["bank_account_id"]), json={})

    assert response.status_code == 422


def test_cashout_read_alone_cannot_reject(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    token = db.open_session()
    try:
        viewer = UserController().ensure_provisioned(
            "user_bank_viewer2", lambda: "bank-viewer2@example.com", lambda: "Viewer"
        )
        grant_permissions(
            viewer.id, PermissionCode.CASHOUT_READ, role_name="viewer_only_2"
        )
        viewer_id = viewer.id
    finally:
        db.close_session(token)

    env.app.dependency_overrides[get_current_user] = lambda: User(id=viewer_id)
    response = env.client.post(
        _reject_path(account["bank_account_id"]), json={"reason": "no"}
    )
    assert response.status_code == 403


def test_customer_cannot_reach_the_admin_endpoints(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()

    assert env.client.get(PENDING).status_code == 403
    assert (
        env.client.post(_verify_path(account["bank_account_id"]), json={}).status_code
        == 403
    )


def test_verification_records_the_admin_and_timestamp(env):
    from remitx_api.models.orm.bank_account import BankAccount

    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()
    env.as_admin()
    env.client.post(_verify_path(account["bank_account_id"]), json={})

    token = db.open_session()
    try:
        row = db.session.get(BankAccount, uuid.UUID(account["bank_account_id"]))
        assert row.verified_by_admin_id == env.admin.id
        assert row.verified_at is not None
        assert row.rejection_reason is None
    finally:
        db.close_session(token)


def test_rejected_account_stays_visible_to_its_owner_with_the_reason(env):
    account = env.client.post(BANK_ACCOUNTS, json=_payload()).json()
    env.as_admin()
    env.client.post(_reject_path(account["bank_account_id"]), json={"reason": "bad"})
    env.as_customer()

    [listed] = env.client.get(BANK_ACCOUNTS).json()
    assert listed["status"] == "rejected"
    assert listed["rejection_reason"] == "bad"
    assert env.client.get(f"{BANK_ACCOUNTS}/withdrawable?currency=ZAR").json() == []


def test_pending_queue_is_oldest_first_and_excludes_decided_accounts(env):
    first = env.client.post(BANK_ACCOUNTS, json=_payload(bank_name="A")).json()
    second = env.client.post(BANK_ACCOUNTS, json=_payload(bank_name="B")).json()
    third = env.client.post(BANK_ACCOUNTS, json=_payload(bank_name="C")).json()

    env.as_admin()
    env.client.post(_verify_path(second["bank_account_id"]), json={})
    ids = [a["bank_account_id"] for a in env.client.get(PENDING).json()]

    assert ids == [first["bank_account_id"], third["bank_account_id"]]


@pytest.mark.parametrize(
    "number, masked", [("1234", "1234"), ("12", "12"), ("12345", "****2345")]
)
def test_short_account_numbers_are_not_padded_with_a_mask(env, number, masked):
    response = env.client.post(BANK_ACCOUNTS, json=_payload(account_number=number))

    assert response.json()["account_number"] == masked


def test_withdrawable_requires_a_currency(env):
    assert env.client.get(f"{BANK_ACCOUNTS}/withdrawable").status_code == 422


def test_optional_fields_can_be_omitted(env):
    payload = _payload()
    del payload["branch_code"], payload["country"]

    response = env.client.post(BANK_ACCOUNTS, json=payload)

    assert response.status_code == 200
    assert response.json()["branch_code"] is None
    assert response.json()["country"] is None


@pytest.mark.parametrize(
    "field", ["account_holder_name", "bank_name", "account_number", "currency"]
)
def test_missing_required_field_is_a_422(env, field):
    payload = _payload()
    del payload[field]

    assert env.client.post(BANK_ACCOUNTS, json=payload).status_code == 422


@pytest.mark.parametrize(
    "field", ["account_holder_name", "bank_name", "account_number", "currency"]
)
def test_blank_required_field_is_refused(env, field):
    response = env.client.post(BANK_ACCOUNTS, json=_payload(**{field: ""}))

    assert response.status_code == 422


def test_unsupported_currency_is_refused(env):
    response = env.client.post(BANK_ACCOUNTS, json=_payload(currency="XYZ"))

    assert response.status_code in (400, 422)
