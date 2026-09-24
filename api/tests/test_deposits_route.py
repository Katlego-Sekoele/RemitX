import uuid

import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.models.orm.account import (
    CURRENCY_USD,
    CURRENCY_ZAR,
)
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.repositories.account_repository import AccountRepository
from tests.platform_account_helpers import seed_platform_accounts
from tests.rbac_helpers import make_user, rbac_client

PROCESS = "/admin/deposits/process"
PENDING = "/admin/deposits/pending"
REFERENCES = "/admin/deposits/account-references"


def _approve_path(deposit_id: str | uuid.UUID) -> str:
    return f"/admin/deposits/{deposit_id}/approve"


@pytest.fixture
def treasury_client():
    """The caller `treasury_operator` exists for: cash-in read *and* confirm."""
    with rbac_client(make_user("treasury"), roles=("treasury_operator",)) as client:
        yield client


def test_caller_without_cashin_permission_is_rejected(client):
    response = client.post(PROCESS, json={"rows": []})

    assert response.status_code == 403


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(PROCESS, json={"rows": []})

    assert response.status_code == 401
    assert anonymous_client.get(REFERENCES).status_code == 401


def test_other_staff_roles_cannot_touch_deposits():
    """The bug this replaced: gating on "is an admin" let every staff role —
    compliance, support, IAM — run the reconciliation job and move money.
    Cash-in is the treasury role's job, and nobody else's.
    """
    with rbac_client(make_user("officer"), roles=("compliance_officer",)) as client:
        assert client.get(PENDING).status_code == 403
        assert client.get(REFERENCES).status_code == 403
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
        assert client.get(REFERENCES).status_code == 200

        blocked = client.post(PROCESS, json={"rows": []})
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == (
            f"Missing permission: {PermissionCode.CASHIN_CONFIRM.value}"
        )
        assert client.post(_approve_path(uuid.uuid4()), json={}).status_code == 403


def test_treasury_operator_confirms_a_matching_row(treasury_client):
    seed_platform_accounts()
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
    [result] = response.json()["processed"]
    assert result["status"] == "confirmed"
    assert result["user_id"] == user_id
    assert result["amount"] == "500.00000000"
    assert result["currency"] == CURRENCY_ZAR


def test_treasury_operator_leaves_an_unmatched_row_pending(treasury_client):
    seed_platform_accounts()

    response = treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {"reference": "remitx deposit", "amount": "80.00", "date": "2026-09-10"}
            ]
        },
    )

    assert response.status_code == 200
    [result] = response.json()["processed"]
    assert result["status"] == "pending"
    assert result["user_id"] is None


def test_pending_endpoint_lists_only_unmatched_deposits(treasury_client):
    seed_platform_accounts()

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
    seed_platform_accounts()
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
    seed_platform_accounts()
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


def test_process_reports_unparseable_dates_without_recording_them(treasury_client):
    seed_platform_accounts()

    response = treasury_client.post(
        PROCESS,
        json={
            "rows": [
                {
                    "reference": "remitx deposit",
                    "amount": "80.00",
                    "date": "not-a-date",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["processed"] == []
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["reason"] == "unparseable_date"
    assert treasury_client.get(PENDING).json() == []


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
    assert "no ZAR bank account" in response.json()["detail"]


def test_treasury_lists_customer_account_references_only(treasury_client):
    user = UserController().ensure_provisioned(
        "user_refs", lambda: "sian@example.com", lambda: "Sian"
    )
    # Platform accounts have no reference, so a statement line can never
    # match one.
    seed_platform_accounts()
    base = user.base_reference
    AccountRepository().get_or_create_user_account(user.id, base, CURRENCY_USD)

    response = treasury_client.get(REFERENCES)

    assert response.status_code == 200
    by_reference = {row["reference"]: row for row in response.json()}
    # No deposit lands on a token account, so its reference is not offered.
    assert set(by_reference) == {f"{base}-usd", f"{base}-zar"}
    assert by_reference[f"{base}-zar"] == {
        "reference": f"{base}-zar",
        "currency": CURRENCY_ZAR,
        "name": "Sian",
    }
    assert by_reference[f"{base}-usd"]["currency"] == CURRENCY_USD
    assert [row["reference"] for row in response.json()] == sorted(by_reference)


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
    seed_platform_accounts()
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


def test_approving_with_a_token_reference_is_a_400(treasury_client):
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_approve_tok_route", lambda: "tok-route@example.com", lambda: "Tok"
    )
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
        json={"account_reference": f"{user.base_reference}-tok"},
    )

    assert response.status_code == 400
    assert "token account" in response.json()["detail"]
    assert treasury_client.get(PENDING).json() == [pending]
