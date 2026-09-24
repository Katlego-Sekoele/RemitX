import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from remitx_api.app import create_app
from remitx_api.auth.dependencies import get_current_user
from remitx_api.config import TestConfig
from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, TYPE_PLATFORM_FIAT, Account
from remitx_api.models.orm.user import User
from remitx_api.repositories.account_repository import AccountRepository
from tests.rbac_helpers import grant_role, seed_rbac_catalogue

BANK_ACCOUNTS = "/bank-accounts"
WITHDRAWALS = "/withdrawals"


def _admin_withdrawals_for_user_path(user_id) -> str:
    return f"/admin/withdrawals/users/{user_id}"


def _bank_account_payload(**overrides) -> dict:
    payload = {
        "account_holder_name": "Test User",
        "bank_name": "First National Bank",
        "account_number": "1234567890",
        "currency": "ZAR",
    }
    payload.update(overrides)
    return payload


@dataclass
class Env:
    """One app, one database, two real persisted callers sharing it — a
    customer and a `payout_operator` admin. Deliberately not two separate
    `create_app(TestConfig)` clients: each call re-runs `db.init(...)` on the
    global `db` singleton (remitx_api/app.py), so a second app silently
    swaps out the database the first client's requests were using. Switching
    `dependency_overrides` on one shared app is what every other test that
    needs more than one caller in the same test should do instead.
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
def env(request):
    """A funded ZAR customer plus a payout_operator admin, with the platform
    ZAR fiat/revenue accounts `POST /withdrawals` needs already seeded.
    `starting_balance` can be overridden with
    `@pytest.mark.parametrize`-free indirect use — see
    `test_insufficient_balance_is_a_400`.
    """
    starting_balance = getattr(request, "param", "1000")

    app = create_app(TestConfig)
    with TestClient(app) as client:
        token = db.open_session()
        try:
            customer = UserController().ensure_provisioned(
                "user_withdraw_customer",
                lambda: "wd-customer@example.com",
                lambda: "Cust",
            )
            seed_rbac_catalogue()
            admin = UserController().ensure_provisioned(
                "user_withdraw_admin", lambda: "wd-admin@example.com", lambda: "Admin"
            )
            grant_role(admin.id, "payout_operator")

            db.session.add(
                Account(
                    user_id=admin.id,
                    type=TYPE_PLATFORM_FIAT,
                    account_currency=CURRENCY_ZAR,
                    label="RemitX SA Bank Account",
                )
            )
            db.session.commit()

            account_repo = AccountRepository()
            zar_account = account_repo.get_user_account(customer.id, CURRENCY_ZAR)
            account_repo.increase_balance(
                zar_account.account_id, Decimal(starting_balance)
            )
            db.session.commit()

            customer_user = User(id=customer.id, base_reference=customer.base_reference)
            admin_user = User(id=admin.id)
        finally:
            db.close_session(token)

        testenv = Env(client=client, app=app, customer=customer_user, admin=admin_user)
        testenv.as_customer()
        yield testenv


def test_anonymous_caller_is_rejected(anonymous_client):
    response = anonymous_client.post(
        WITHDRAWALS,
        json={"bank_account_id": str(uuid.uuid4()), "currency": "ZAR", "amount": "10"},
    )

    assert response.status_code == 401


def test_withdrawal_into_a_verified_account_settles_immediately(env):
    bank_account = env.client.post(BANK_ACCOUNTS, json=_bank_account_payload()).json()

    env.as_admin()
    verify_response = env.client.post(
        f"/admin/bank-accounts/{bank_account['bank_account_id']}/verify", json={}
    )
    assert verify_response.status_code == 200

    env.as_customer()
    response = env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": bank_account["bank_account_id"],
            "currency": "ZAR",
            "amount": "100.00",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["gross_amount"] == "100.00000000"
    assert body["fee_amount"] == "0.75000000"
    assert body["net_amount"] == "99.25000000"
    assert body["confirmed_by"] == "system"

    accounts_response = env.client.get("/accounts")
    zar = next(a for a in accounts_response.json() if a["currency"] == "ZAR")
    assert zar["available_balance"] == "900.00000000"


def test_withdrawal_into_an_unverified_account_is_refused(env):
    """No admin processing queue any more — a withdrawal against a bank
    account that isn't verified yet is refused outright, not held pending.
    The frontend never offers such an account as a choice in the first
    place (`GET /bank-accounts/withdrawable`); this only matters for a
    direct API call or a race against verification."""
    bank_account = env.client.post(BANK_ACCOUNTS, json=_bank_account_payload()).json()

    response = env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": bank_account["bank_account_id"],
            "currency": "ZAR",
            "amount": "100.00",
        },
    )

    assert response.status_code == 400

    # Nothing was held — the whole balance is still available.
    accounts_response = env.client.get("/accounts")
    zar = next(a for a in accounts_response.json() if a["currency"] == "ZAR")
    assert zar["available_balance"] == "1000.00000000"


@pytest.mark.parametrize("env", ["10"], indirect=True)
def test_insufficient_balance_is_a_400(env):
    bank_account = env.client.post(BANK_ACCOUNTS, json=_bank_account_payload()).json()

    response = env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": bank_account["bank_account_id"],
            "currency": "ZAR",
            "amount": "100.00",
        },
    )

    assert response.status_code == 400


def test_unknown_bank_account_is_a_400(env):
    response = env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": str(uuid.uuid4()),
            "currency": "ZAR",
            "amount": "10.00",
        },
    )

    assert response.status_code == 400


def _verify(env, bank_account_id) -> None:
    env.as_admin()
    response = env.client.post(
        f"/admin/bank-accounts/{bank_account_id}/verify", json={}
    )
    assert response.status_code == 200
    env.as_customer()


def test_second_withdrawal_cannot_exceed_available_balance(env):
    bank_account = env.client.post(BANK_ACCOUNTS, json=_bank_account_payload()).json()
    _verify(env, bank_account["bank_account_id"])

    first = env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": bank_account["bank_account_id"],
            "currency": "ZAR",
            "amount": "600.00",
        },
    )
    assert first.status_code == 200
    assert first.json()["status"] == "confirmed"

    second = env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": bank_account["bank_account_id"],
            "currency": "ZAR",
            "amount": "600.00",
        },
    )

    assert second.status_code == 400


def test_admin_can_list_a_users_withdrawals(env):
    """The admin portal's user-profile page: an operator viewing a
    customer's withdrawal history."""
    bank_account = env.client.post(BANK_ACCOUNTS, json=_bank_account_payload()).json()
    _verify(env, bank_account["bank_account_id"])

    withdrawal = env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": bank_account["bank_account_id"],
            "currency": "ZAR",
            "amount": "100.00",
        },
    ).json()

    env.as_admin()
    response = env.client.get(_admin_withdrawals_for_user_path(env.customer.id))

    assert response.status_code == 200
    [body] = response.json()
    assert body["withdrawal_id"] == withdrawal["withdrawal_id"]
    assert body["status"] == "confirmed"


def test_admin_listing_for_a_user_with_no_withdrawals_is_empty(env):
    env.as_admin()
    response = env.client.get(_admin_withdrawals_for_user_path(env.customer.id))

    assert response.status_code == 200
    assert response.json() == []


def _verified_bank_account(env, **overrides) -> dict:
    bank_account = env.client.post(
        BANK_ACCOUNTS, json=_bank_account_payload(**overrides)
    ).json()
    _verify(env, bank_account["bank_account_id"])
    return bank_account


def _withdraw(env, bank_account_id, amount, currency="ZAR"):
    return env.client.post(
        WITHDRAWALS,
        json={
            "bank_account_id": bank_account_id,
            "currency": currency,
            "amount": amount,
        },
    )


def _available_zar(env) -> str:
    accounts = env.client.get("/accounts").json()
    return next(a for a in accounts if a["currency"] == "ZAR")["available_balance"]


def test_withdrawal_moves_the_gross_amount_into_the_platform_fiat_account(env):
    """Both legs (net + fee) credit the same RemitX ZAR fiat account, so it
    gains the full gross amount; both transactions end up confirmed."""
    from remitx_api.models.orm.transaction import Transaction
    from remitx_api.models.orm.withdrawal import Withdrawal

    bank_account = _verified_bank_account(env)
    body = _withdraw(env, bank_account["bank_account_id"], "100.00").json()

    token = db.open_session()
    try:
        platform = AccountRepository().get_platform_account(
            TYPE_PLATFORM_FIAT, CURRENCY_ZAR
        )
        assert platform.account_balance == Decimal("100")

        withdrawal = db.session.get(Withdrawal, uuid.UUID(body["withdrawal_id"]))
        net_tx = db.session.get(Transaction, withdrawal.tx_id)
        fee_tx = db.session.get(Transaction, withdrawal.fee_tx_id)
        assert net_tx.type == "withdrawal"
        assert net_tx.amount == Decimal("99.25")
        assert net_tx.status == "confirmed"
        assert fee_tx.type == "fee"
        assert fee_tx.amount == Decimal("0.75")
        assert fee_tx.status == "confirmed"
    finally:
        db.close_session(token)


def test_withdrawal_whose_fee_rounds_to_zero_is_charged_the_minimum_fee(env):
    """0.0075 * 0.50 = 0.00375 -> 0.00, so the 0.01 minimum fee applies and a
    fee leg is still written."""
    from remitx_api.models.orm.transaction import Transaction
    from remitx_api.models.orm.withdrawal import Withdrawal

    bank_account = _verified_bank_account(env)
    response = _withdraw(env, bank_account["bank_account_id"], "0.50")

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["fee_amount"]) == Decimal("0.01")
    assert Decimal(body["net_amount"]) == Decimal("0.49")
    assert body["status"] == "confirmed"

    token = db.open_session()
    try:
        withdrawal = db.session.get(Withdrawal, uuid.UUID(body["withdrawal_id"]))
        fee_tx = db.session.get(Transaction, withdrawal.fee_tx_id)
        assert fee_tx.type == "fee"
        assert fee_tx.amount == Decimal("0.01")
        assert fee_tx.status == "confirmed"
    finally:
        db.close_session(token)
    assert _available_zar(env) == "999.50000000"


def test_smallest_withdrawal_pays_out_one_cent(env):
    bank_account = _verified_bank_account(env)
    response = _withdraw(env, bank_account["bank_account_id"], "0.02")

    assert response.status_code == 200
    body = response.json()
    assert Decimal(body["fee_amount"]) == Decimal("0.01")
    assert Decimal(body["net_amount"]) == Decimal("0.01")


def test_amount_is_rounded_to_two_decimal_places(env):
    bank_account = _verified_bank_account(env)
    response = _withdraw(env, bank_account["bank_account_id"], "100.005")

    assert response.status_code == 200
    assert Decimal(response.json()["gross_amount"]) == Decimal("100.01")


def test_withdrawing_the_exact_available_balance_is_allowed(env):
    bank_account = _verified_bank_account(env)
    response = _withdraw(env, bank_account["bank_account_id"], "1000.00")

    assert response.status_code == 200
    assert _available_zar(env) == "0E-8" or Decimal(_available_zar(env)) == 0


@pytest.mark.parametrize("amount", ["0", "-100.00", "0.004", "0.01"])
def test_amount_below_the_minimum_is_refused(env, amount):
    """Zero, negative, or anything under 0.02 must be a client error — never
    reach the ledger (a negative withdrawal would otherwise *credit* the
    customer, and 0.01 would be eaten entirely by the minimum fee)."""
    bank_account = _verified_bank_account(env)
    response = _withdraw(env, bank_account["bank_account_id"], amount)

    assert response.status_code in (400, 422)
    assert Decimal(_available_zar(env)) == Decimal("1000")


def test_withdrawal_into_a_rejected_account_is_a_409(env):
    bank_account = env.client.post(BANK_ACCOUNTS, json=_bank_account_payload()).json()
    env.as_admin()
    env.client.post(
        f"/admin/bank-accounts/{bank_account['bank_account_id']}/reject",
        json={"reason": "mismatch"},
    )
    env.as_customer()

    response = _withdraw(env, bank_account["bank_account_id"], "100.00")

    assert response.status_code == 409
    assert _available_zar(env) == "1000.00000000"


def test_withdrawal_into_another_users_verified_account_is_a_400(env):
    from remitx_api.services import bank_account_service

    token = db.open_session()
    try:
        other = UserController().ensure_provisioned(
            "user_withdraw_other", lambda: "wd-other@example.com", lambda: "Other"
        )
        other_account = bank_account_service.add_bank_account(
            other.id, "Someone Else", "Standard Bank", "5555555555", "ZAR"
        )
        bank_account_service.verify_bank_account(
            other_account.bank_account_id, env.admin.id
        )
        other_account_id = str(other_account.bank_account_id)
    finally:
        db.close_session(token)

    response = _withdraw(env, other_account_id, "100.00")

    assert response.status_code == 400
    assert _available_zar(env) == "1000.00000000"


def test_currency_not_matching_the_bank_account_is_a_400(env):
    bank_account = _verified_bank_account(env, currency="USD")

    response = _withdraw(env, bank_account["bank_account_id"], "10.00", "ZAR")

    assert response.status_code == 400


def test_withdrawing_into_a_currency_the_user_has_no_account_in_is_a_400(env):
    """A verified USD bank account, but the customer only holds ZAR + token
    accounts."""
    bank_account = _verified_bank_account(env, currency="USD")

    response = _withdraw(env, bank_account["bank_account_id"], "10.00", "USD")

    assert response.status_code == 400


def test_withdrawing_the_token_balance_directly_is_a_400(env):
    from remitx_api.models.orm.account import CURRENCY_TOKEN

    # A token-currency bank account can't be added in the first place, and
    # the token check runs before the bank account is looked up.
    response = _withdraw(env, str(uuid.uuid4()), "10.00", CURRENCY_TOKEN)

    assert response.status_code == 400


def test_malformed_payload_is_a_422(env):
    assert env.client.post(WITHDRAWALS, json={}).status_code == 422
    assert (
        env.client.post(
            WITHDRAWALS,
            json={"bank_account_id": "not-a-uuid", "currency": "ZAR", "amount": "1"},
        ).status_code
        == 422
    )
    assert _withdraw(env, str(uuid.uuid4()), "not-a-number").status_code == 422


def test_customer_lists_only_their_own_withdrawals_newest_first(env):
    bank_account = _verified_bank_account(env)
    first = _withdraw(env, bank_account["bank_account_id"], "10.00").json()
    second = _withdraw(env, bank_account["bank_account_id"], "20.00").json()

    response = env.client.get(WITHDRAWALS)

    assert response.status_code == 200
    ids = [w["withdrawal_id"] for w in response.json()]
    assert ids == [second["withdrawal_id"], first["withdrawal_id"]]

    env.as_admin()
    assert env.client.get(WITHDRAWALS).json() == []


def test_anonymous_caller_cannot_list_withdrawals(anonymous_client):
    assert anonymous_client.get(WITHDRAWALS).status_code == 401


def test_admin_withdrawal_listing_needs_cashout_read(client):
    response = client.get(_admin_withdrawals_for_user_path(uuid.uuid4()))

    assert response.status_code == 403


def test_settling_an_already_settled_withdrawal_is_refused(env):
    """The guarded pending -> confirmed transition stops a double settle
    from moving the balances twice."""
    from remitx_api.models.orm.withdrawal import Withdrawal
    from remitx_api.services import withdrawal_service

    bank_account = _verified_bank_account(env)
    body = _withdraw(env, bank_account["bank_account_id"], "100.00").json()

    token = db.open_session()
    try:
        withdrawal = db.session.get(Withdrawal, uuid.UUID(body["withdrawal_id"]))
        with pytest.raises(withdrawal_service.WithdrawalNotPendingError):
            withdrawal_service._settle_withdrawal(withdrawal, confirmed_by="system")
        db.session.rollback()
    finally:
        db.close_session(token)

    assert _available_zar(env) == "900.00000000"
