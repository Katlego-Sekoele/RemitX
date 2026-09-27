"""`GET /admin/platform-accounts`: RemitX's own balances, for treasurers."""

from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR
from remitx_api.models.orm.permission import PermissionCode
from remitx_api.models.orm.platform_account_seed import (
    ISSUER_LABEL,
    TREASURY_WALLET_LABEL,
)
from remitx_api.models.orm.transaction import STATUS_PENDING, TYPE_FEE, Transaction
from remitx_api.repositories.account_repository import AccountRepository
from tests.platform_account_helpers import seed_platform_accounts
from tests.rbac_helpers import make_user, rbac_client

PLATFORM_ACCOUNTS = "/admin/platform-accounts"


def test_every_treasurer_sees_the_platform_accounts_in_display_order():
    with rbac_client(make_user("treasurer"), roles=("treasury_operator",)) as client:
        seed_platform_accounts()

        response = client.get(PLATFORM_ACCOUNTS)

    assert response.status_code == 200
    assert [account["label"] for account in response.json()] == [
        "RemitX SA Bank Account",
        "RemitX BW Bank Account",
        "RemitX EU Bank Account",
        "RemitX UK Bank Account",
        "RemitX LES Bank Account",
        "RemitX MAL Bank Account",
        "RemitX MOZ Bank Account",
        "RemitX NAM Bank Account",
        "RemitX US Bank Account",
        "RemitX ZIM Bank Account",
        "RemitX SA Fee Revenue",
        "RemitX BW Fee Revenue",
        "RemitX EU Fee Revenue",
        "RemitX UK Fee Revenue",
        "RemitX LES Fee Revenue",
        "RemitX MAL Fee Revenue",
        "RemitX MOZ Fee Revenue",
        "RemitX NAM Fee Revenue",
        "RemitX US Fee Revenue",
        "RemitX ZIM Fee Revenue",
        TREASURY_WALLET_LABEL,
        ISSUER_LABEL,
    ]
    by_label = {account["label"]: account for account in response.json()}
    assert by_label["RemitX SA Bank Account"] == {
        "account_id": by_label["RemitX SA Bank Account"]["account_id"],
        "label": "RemitX SA Bank Account",
        "type": "REMITX_FIAT",
        "currency": CURRENCY_ZAR,
        "kind": "fiat",
        "balance": "0.00",
        "available_balance": "0.00",
    }
    assert by_label[TREASURY_WALLET_LABEL]["kind"] == "settlement"
    assert by_label[ISSUER_LABEL]["type"] == "EXTERNAL"


def test_customer_accounts_are_not_platform_accounts():
    with rbac_client(make_user("treasurer"), roles=("treasury_operator",)) as client:
        seed_platform_accounts()
        UserController().ensure_provisioned(
            "user_platform_customer", lambda: "customer@example.com", lambda: "Cu"
        )

        response = client.get(PLATFORM_ACCOUNTS)

    assert all(account["type"] != "USER" for account in response.json())
    assert len(response.json()) == 22


def test_available_balance_nets_out_pending_outgoing_legs():
    with rbac_client(make_user("treasurer"), roles=("treasury_operator",)) as client:
        accounts = seed_platform_accounts()
        bank = accounts["RemitX SA Bank Account"]
        revenue = accounts["RemitX SA Fee Revenue"]
        AccountRepository().increase_balance(bank.account_id, Decimal("100"))
        db.session.add(
            Transaction(
                type=TYPE_FEE,
                credit_account_id=bank.account_id,
                debit_account_id=revenue.account_id,
                amount=Decimal("15"),
                currency=CURRENCY_ZAR,
                status=STATUS_PENDING,
            )
        )
        db.session.commit()

        response = client.get(PLATFORM_ACCOUNTS)

    sa_bank = next(
        account
        for account in response.json()
        if account["label"] == "RemitX SA Bank Account"
    )
    assert sa_bank["balance"] == "100.00"
    assert sa_bank["available_balance"] == "85.00"


def test_staff_without_platform_account_read_are_refused():
    """Deposits staff outside treasury, and every other staff role, see no
    platform balances."""
    for role in ("compliance_officer", "support_agent", "payout_operator"):
        with rbac_client(make_user(role), roles=(role,)) as client:
            response = client.get(PLATFORM_ACCOUNTS)

        assert response.status_code == 403, role
        assert response.json()["detail"] == (
            f"Missing permission: {PermissionCode.PLATFORM_ACCOUNT_READ.value}"
        )


def test_a_customer_is_refused(client):
    assert client.get(PLATFORM_ACCOUNTS).status_code == 403
