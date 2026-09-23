from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_PLATFORM_FIAT,
    Account,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services import deposit_service


def _seed_bank_account() -> Account:
    """Platform accounts are admin-owned (Transaction_Flow_Context.md §1) —
    stand in for `scripts/seed_platform_accounts.py` with a throwaway admin.
    """
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


def test_matching_zar_reference_confirms_and_credits_immediately(app_context):
    _seed_bank_account()
    user = UserController().ensure_provisioned(
        "user_dep", lambda: "dep@example.com", lambda: "Dep"
    )
    zar_reference = f"{user.base_reference}-zar"

    deposits = deposit_service.process_deposits(
        [{"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"}]
    )

    assert len(deposits) == 1
    assert deposits[0].user_id == user.id
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("500.00")


def test_token_reference_matches_its_own_account(app_context):
    """A reference is matched purely on its own (globally unique) value —
    a statement line quoting a user's uctusd reference resolves to their
    token account, not their ZAR one.
    """
    _seed_bank_account()
    user = UserController().ensure_provisioned(
        "user_tok", lambda: "tok@example.com", lambda: "Tok"
    )
    token_reference = f"{user.base_reference}-tok"

    deposits = deposit_service.process_deposits(
        [{"reference": token_reference, "amount": "500.00", "date": "2026-09-10"}]
    )

    assert len(deposits) == 1
    assert deposits[0].user_id == user.id
    token_account = AccountRepository().get_user_account(user.id, CURRENCY_TOKEN)
    assert token_account.account_balance == Decimal("500.00")


def test_reprocessing_the_same_statement_line_does_not_credit_again(app_context):
    """Uploading the same CSV twice, or an overlapping date range, must not
    create a second deposit or move the balance again.
    """
    _seed_bank_account()
    user = UserController().ensure_provisioned(
        "user_dedup", lambda: "dedup@example.com", lambda: "Dedup"
    )
    zar_reference = f"{user.base_reference}-zar"
    line = {"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"}

    first = deposit_service.process_deposits([line])
    second = deposit_service.process_deposits([line, dict(line)])

    assert len(first) == 1
    assert second == []
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("500.00")
    assert len(deposit_service.get_deposits_for_user(user.id)) == 1

    later = deposit_service.process_deposits(
        [{"reference": zar_reference, "amount": "10.00", "date": "2026-09-10"}]
    )
    assert len(later) == 1
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("510.00")


def test_reprocessing_an_unmatched_line_does_not_queue_it_twice(app_context):
    _seed_bank_account()
    line = {"reference": "not-a-person", "amount": "80.00", "date": "2026-09-09"}

    deposit_service.process_deposits([line])
    deposit_service.process_deposits([line])

    assert len(deposit_service.get_pending_deposits()) == 1


def test_outgoing_lines_are_skipped_not_recorded_as_deposits(app_context):
    """A real statement mixes RemitX's own outgoing payments in with sender
    deposits — a negative amount was never a deposit and must not become one
    (transactions.amount is never negative, checked at the DB level).
    """
    _seed_bank_account()
    user = UserController().ensure_provisioned(
        "user_mixed", lambda: "mixed@example.com", lambda: "Mixed"
    )
    zar_reference = f"{user.base_reference}-zar"

    deposits = deposit_service.process_deposits(
        [
            {"reference": "SALARY-SEP26", "amount": "-18500.00", "date": "2026-09-08"},
            {"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"},
        ]
    )

    assert len(deposits) == 1
    assert deposits[0].user_id == user.id
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("500.00")
