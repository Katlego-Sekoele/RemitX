import uuid

import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, TYPE_PLATFORM_FIAT, Account
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.services import deposit_service
from tests.rbac_helpers import make_user, rbac_client

PROCESS = "/admin/deposits/process"
PENDING = "/admin/deposits/pending"


def _approve_path(deposit_id: str | uuid.UUID) -> str:
    return f"/admin/deposits/{deposit_id}/approve"


@pytest.fixture
def treasury_client():
    """The caller `treasury_operator` exists for: cash-in read *and* confirm."""
    with rbac_client(make_user("treasury"), roles=("treasury_operator",)) as client:
        yield client


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


def test_caller_without_cashin_permission_is_rejected(client):
    response = client.post(PROCESS, json={"rows": []})

    assert response.status_code == 403


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(PROCESS, json={"rows": []})

    assert response.status_code == 401


def test_other_staff_roles_cannot_touch_deposits():
    """The bug this replaced: gating on "is an admin" let every staff role —
    compliance, support, IAM — run the reconciliation job and move money.
    Cash-in is the treasury role's job, and nobody else's.
    """
    with rbac_client(make_user("officer"), roles=("compliance_officer",)) as client:
        assert client.get(PENDING).status_code == 403
        assert client.post(PROCESS, json={"rows": []}).status_code == 403
        assert client.post(_approve_path(uuid.uuid4()), json={}).status_code == 403


def test_reading_the_queue_does_not_grant_confirming_it():
    """`cashin:read` is the router's baseline; the two mutating routes
    escalate on top of it, so read-only access stops at the list.
    """
    with rbac_client(
        make_user("viewer"), permissions=(PermissionCode.CASHIN_READ,)
    ) as client:
        assert client.get(PENDING).status_code == 200

        blocked = client.post(PROCESS, json={"rows": []})
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == (
            f"Missing permission: {PermissionCode.CASHIN_CONFIRM.value}"
        )
        assert client.post(_approve_path(uuid.uuid4()), json={}).status_code == 403


def test_treasury_operator_confirms_a_matching_row(treasury_client):
    _seed_bank_account()
    user = UserController().ensure_provisioned(
        "user_dep_route", lambda: "dep@example.com", lambda: "Dep"
    )
    zar_reference = f"{user.base_reference}-zar"
    user_id = str(user.id)

    response = treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"}
            ]
        },
    )

    assert response.status_code == 200
    [result] = response.json()
    assert result["status"] == "confirmed"
    assert result["user_id"] == user_id
    assert result["amount"] == "500.00000000"
    assert result["currency"] == CURRENCY_ZAR


def test_treasury_operator_leaves_an_unmatched_row_pending(treasury_client):
    _seed_bank_account()

    response = treasury_client.post(
        PROCESS,
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


def test_pending_endpoint_lists_only_unmatched_deposits(treasury_client):
    _seed_bank_account()

    treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-10"}
            ]
        },
    )

    response = treasury_client.get(PENDING)

    assert response.status_code == 200
    [result] = response.json()
    assert result["reference"] == "remitx deposit"
    assert result["amount"] == "80.00000000"
    assert result["created_at"].endswith("+00:00")


def test_treasury_operator_approves_a_pending_deposit(treasury_client):
    _seed_bank_account()
    user = UserController().ensure_provisioned(
        "user_approve_route", lambda: "approve@example.com", lambda: "App"
    )
    user_id = str(user.id)

    treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-10"}
            ]
        },
    )
    [pending] = treasury_client.get(PENDING).json()

    response = treasury_client.post(
        _approve_path(pending["deposit_id"]),
        json={"account_reference": f"{user.base_reference}-zar"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "confirmed"
    assert result["user_id"] == user_id
    assert treasury_client.get(PENDING).json() == []


def test_approval_records_the_operator_who_confirmed_it(treasury_client):
    """`confirmed_by` is the caller's own id — the route still needs the
    authenticated user for the audit trail, just not to decide access.
    """
    _seed_bank_account()
    user = UserController().ensure_provisioned(
        "user_approve_audit", lambda: "audit@example.com", lambda: "Aud"
    )

    treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-10"}
            ]
        },
    )
    [pending] = treasury_client.get(PENDING).json()

    response = treasury_client.post(
        _approve_path(pending["deposit_id"]),
        json={"account_reference": f"  {user.base_reference}-ZAR  "},
    )

    assert response.status_code == 200
    assert response.json()["confirmed_by"] not in (None, "system")


def test_process_without_a_platform_bank_account_is_refused(treasury_client):
    response = treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {"reference": "someone-zar", "amount": "10.00", "date": "2026-09-10"}
            ]
        },
    )

    assert response.status_code == 409
    assert "RemitX SA Bank Account" in response.json()["detail"]


def test_approving_an_unknown_deposit_is_a_400(treasury_client):
    user = UserController().ensure_provisioned(
        "user_approve_missing", lambda: "missing@example.com", lambda: "Miss"
    )

    response = treasury_client.post(
        _approve_path(uuid.uuid4()),
        json={"account_reference": f"{user.base_reference}-zar"},
    )

    assert response.status_code == 400


def test_approving_with_an_unknown_reference_is_a_400(treasury_client):
    _seed_bank_account()
    treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-11"}
            ]
        },
    )
    [pending] = treasury_client.get(PENDING).json()

    response = treasury_client.post(
        _approve_path(pending["deposit_id"]),
        json={"account_reference": "nobody1-zar"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "No RemitX account has that reference."
    assert treasury_client.get(PENDING).json() != []
