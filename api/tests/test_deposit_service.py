from decimal import Decimal

import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.errors.deposits import TokenAccountDepositError
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_PLATFORM_FIAT,
    create_account_reference,
)
from remitx_api.models.orm.transaction import STATUS_CONFIRMED
from remitx_api.models.schemas.deposit import SkippedStatementLineReason
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import deposit_service
from tests.platform_account_helpers import seed_platform_accounts

FOREIGN_CURRENCIES = (CURRENCY_USD, CURRENCY_ZWL, CURRENCY_NAD)


def _bank_balance(currency: str) -> Decimal:
    return (
        AccountRepository()
        .get_platform_account(TYPE_PLATFORM_FIAT, currency)
        .account_balance
    )


def _assert_deposited_in(deposit, currency: str, amount: str) -> None:
    """The deposit is one confirmed transaction in `currency`, out of RemitX's
    bank account in `currency` into the customer's account in it."""
    accounts = AccountRepository()
    transaction = TransactionRepository().get_by_id(deposit.tx_id)
    source = accounts.get_by_id(transaction.credit_account_id)
    destination = accounts.get_by_id(transaction.debit_account_id)
    assert transaction.status == STATUS_CONFIRMED
    assert transaction.currency == currency
    assert source.type == TYPE_PLATFORM_FIAT
    assert source.account_currency == currency
    assert destination.user_id == deposit.user_id
    assert destination.account_currency == currency
    assert destination.account_balance == Decimal(amount)
    assert source.account_balance == -Decimal(amount)


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


@pytest.mark.parametrize("currency", FOREIGN_CURRENCIES)
def test_fiat_reference_credits_that_account_in_its_currency(app_context, currency):
    """A deposit quoting a customer's USD, ZWL or NAD reference is money in
    that currency: it comes out of RemitX's bank account in it, never out of
    the ZAR one, and leaves their ZAR balance alone.
    """
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_fx_dep", lambda: "fx-dep@example.com", lambda: "Fx"
    )
    AccountRepository().get_or_create_user_account(
        user.id, user.base_reference, currency
    )
    reference = create_account_reference(user.base_reference, currency)

    result = deposit_service.process_deposits(
        [{"reference": reference, "amount": "500.00", "date": "2026-09-10"}]
    )

    [deposit] = result.deposits
    assert deposit.user_id == user.id
    _assert_deposited_in(deposit, currency, "500.00")
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("0")
    assert _bank_balance(CURRENCY_ZAR) == Decimal("0")


def test_token_reference_is_left_pending(app_context):
    """No deposit lands on a token account. A line quoting one waits for an
    admin, and no balance moves.
    """
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_tok", lambda: "tok@example.com", lambda: "Tok"
    )
    token_reference = f"{user.base_reference}-tok"

    result = deposit_service.process_deposits(
        [{"reference": token_reference, "amount": "500.00", "date": "2026-09-10"}]
    )

    [deposit] = result.deposits
    assert deposit.user_id is None
    assert deposit_service.get_pending_deposits() == [deposit]
    accounts = AccountRepository()
    assert accounts.get_user_account(user.id, CURRENCY_TOKEN).account_balance == 0
    assert accounts.get_user_account(user.id, CURRENCY_ZAR).account_balance == 0


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


def test_approving_by_zar_reference_credits_the_zar_account(app_context):
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_approve_zar", lambda: "approve-zar@example.com", lambda: "Zar"
    )
    admin = UserController().ensure_provisioned(
        "user_admin_approve", lambda: "admin-approve@example.com", lambda: "Adm"
    )
    deposit_service.process_deposits(
        [{"reference": "not-a-person", "amount": "80.00", "date": "2026-09-11"}]
    )
    [pending] = deposit_service.get_pending_deposits()

    deposit = deposit_service.approve_pending_deposit(
        pending.deposit_id, f"{user.base_reference}-ZAR", admin.id
    )

    _assert_deposited_in(deposit, CURRENCY_ZAR, "80.00")
    assert deposit_service.get_pending_deposits() == []


@pytest.mark.parametrize("currency", FOREIGN_CURRENCIES)
def test_approving_by_fiat_reference_credits_that_account_in_its_currency(
    app_context, currency
):
    """An unmatched line waits in ZAR against RemitX SA. The account the
    admin names decides its currency: the transaction moves to RemitX's bank
    account in that currency, and the customer's ZAR balance stays put.
    """
    seed_platform_accounts()
    user = UserController().ensure_provisioned(
        "user_approve_fx", lambda: "approve-fx@example.com", lambda: "Fx"
    )
    AccountRepository().get_or_create_user_account(
        user.id, user.base_reference, currency
    )
    admin = UserController().ensure_provisioned(
        "user_admin_approve", lambda: "admin-approve@example.com", lambda: "Adm"
    )
    deposit_service.process_deposits(
        [{"reference": "not-a-person", "amount": "80.00", "date": "2026-09-11"}]
    )
    [pending] = deposit_service.get_pending_deposits()

    deposit = deposit_service.approve_pending_deposit(
        pending.deposit_id,
        create_account_reference(user.base_reference, currency),
        admin.id,
    )

    assert deposit.user_id == user.id
    _assert_deposited_in(deposit, currency, "80.00")
    zar_account = AccountRepository().get_user_account(user.id, CURRENCY_ZAR)
    assert zar_account.account_balance == Decimal("0")
    assert _bank_balance(CURRENCY_ZAR) == Decimal("0")
    assert deposit_service.get_pending_deposits() == []


def test_approving_by_token_reference_is_refused(app_context):
    """The admin must name a fiat account. The deposit stays pending and no
    balance moves.
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
    [pending] = deposit_service.get_pending_deposits()

    with pytest.raises(TokenAccountDepositError):
        deposit_service.approve_pending_deposit(
            pending.deposit_id, f"{user.base_reference}-TOK", admin.id
        )

    accounts = AccountRepository()
    assert accounts.get_user_account(user.id, CURRENCY_TOKEN).account_balance == 0
    assert accounts.get_user_account(user.id, CURRENCY_ZAR).account_balance == 0
    assert deposit_service.get_pending_deposits() == [pending]


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
