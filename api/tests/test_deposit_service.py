from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
)
from remitx_api.models.schemas.deposit import SkippedStatementLineReason
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.services import deposit_service
from tests.platform_account_helpers import seed_platform_accounts


def test_matching_zar_reference_confirms_and_credits_immediately(app_context):
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_dep", lambda: "dep@example.com", lambda: "Dep"
    )
    zar_reference = f"{user.base_reference}-zar"

    result = deposit_service.process_deposits(
        [{"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"}]
    )

    assert len(result.deposits) == 1
    assert result.deposits[0].user_id == user.id
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("500.00")


def test_token_reference_matches_its_own_account(app_context):
    """A reference is matched purely on its own (globally unique) value —
    a statement line quoting a user's uctusd reference resolves to their
    token account, not their ZAR one.
    """
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_tok", lambda: "tok@example.com", lambda: "Tok"
    )
    token_reference = f"{user.base_reference}-tok"

    result = deposit_service.process_deposits(
        [{"reference": token_reference, "amount": "500.00", "date": "2026-09-10"}]
    )

    assert len(result.deposits) == 1
    assert result.deposits[0].user_id == user.id
    token_account = AccountRepository().get_user_account(user.id, CURRENCY_TOKEN)
    assert token_account.account_balance == Decimal("500.00")


def test_reprocessing_the_same_statement_line_does_not_credit_again(app_context):
    """Uploading the same CSV twice, or an overlapping date range, must not
    create a second deposit or move the balance again.
    """
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_dedup", lambda: "dedup@example.com", lambda: "Dedup"
    )
    zar_reference = f"{user.base_reference}-zar"
    line = {"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"}

    first = deposit_service.process_deposits([line])
    second = deposit_service.process_deposits([line, dict(line)])

    assert len(first.deposits) == 1
    assert second.deposits == []
    assert len(second.skipped) == 2
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("500.00")
    assert len(deposit_service.get_deposits_for_user(user.id)) == 1

    later = deposit_service.process_deposits(
        [{"reference": zar_reference, "amount": "10.00", "date": "2026-09-10"}]
    )
    assert len(later.deposits) == 1
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("510.00")


def test_reprocessing_an_unmatched_line_does_not_queue_it_twice(app_context):
    seed_platform_accounts()
    line = {"reference": "not-a-person", "amount": "80.00", "date": "2026-09-09"}

    deposit_service.process_deposits([line])
    again = deposit_service.process_deposits([line])

    assert len(deposit_service.get_pending_deposits()) == 1
    assert len(again.skipped) == 1


def test_approving_by_token_reference_credits_the_token_account(app_context):
    """The reference identifies the account. A token reference credits the
    token balance, not ZAR.
    """
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_approve_tok", lambda: "approve-tok@example.com", lambda: "Tok"
    )
    admin = UserController().ensure_provisioned(
        "user_admin_approve", lambda: "admin-approve@example.com", lambda: "Adm"
    )
    deposit_service.process_deposits(
        [{"reference": "not-a-person", "amount": "80.00", "date": "2026-09-11"}]
    )
    pending = deposit_service.get_pending_deposits()[0]

    deposit_service.approve_pending_deposit(
        pending.deposit_id, f"{user.base_reference}-TOK", admin.id
    )

    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    token_account = AccountRepository().get_user_account(user.id, CURRENCY_TOKEN)
    assert zar_account.account_balance == Decimal("0")
    assert token_account.account_balance == Decimal("80.00")
    assert deposit_service.get_pending_deposits() == []


def test_unparseable_statement_date_is_skipped(app_context):
    seed_platform_accounts()

    result = deposit_service.process_deposits(
        [{"reference": "remitx deposit", "amount": "80.00", "date": "not-a-date"}]
    )

    assert result.deposits == []
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == SkippedStatementLineReason.UNPARSEABLE_DATE
    assert deposit_service.get_pending_deposits() == []


def test_outgoing_lines_are_skipped_not_recorded_as_deposits(app_context):
    """A real statement mixes RemitX's own outgoing payments in with sender
    deposits — a negative amount was never a deposit and must not become one
    (transactions.amount is never negative, checked at the DB level).
    """
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_mixed", lambda: "mixed@example.com", lambda: "Mixed"
    )
    zar_reference = f"{user.base_reference}-zar"

    result = deposit_service.process_deposits(
        [
            {"reference": "SALARY-SEP26", "amount": "-18500.00", "date": "2026-09-08"},
            {"reference": zar_reference, "amount": "500.00", "date": "2026-09-10"},
        ]
    )

    assert len(result.deposits) == 1
    assert result.deposits[0].user_id == user.id
    assert len(result.skipped) == 1
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("500.00")
