from decimal import Decimal

import pytest
from remitx_api.controllers.user_controller import UserController
from remitx_api.errors.deposits import DepositCurrencyMismatchError
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_NAD,
    CURRENCY_TOKEN,
    CURRENCY_USD,
    CURRENCY_ZAR,
    CURRENCY_ZWL,
    TYPE_PLATFORM_FIAT,
    create_account_reference,
)
from remitx_api.models.orm.audit_log import AuditAction, AuditLog
from remitx_api.models.orm.transaction import STATUS_CONFIRMED, STATUS_PENDING
from remitx_api.models.schemas.deposit import SkippedStatementLineReason
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.services import deposit_service
from sqlalchemy import select
from tests.platform_account_helpers import seed_platform_accounts

FOREIGN_CURRENCIES = (CURRENCY_USD, CURRENCY_ZWL, CURRENCY_NAD)


def _customer(name: str, *currencies: str):
    """A signed-up customer (ZAR + token accounts), plus an account in each
    of `currencies`."""
    user = UserController().ensure_provisioned(
        f"user_{name}", lambda: f"{name}@example.com", lambda: "Sipho"
    )
    for currency in currencies:
        AccountRepository().get_or_create_user_account(
            user.id, user.base_reference, currency
        )
    return user


def _admin():
    return UserController().ensure_provisioned(
        "user_admin_approve", lambda: "admin-approve@example.com", lambda: "Adm"
    )


def _balance(user, currency: str) -> Decimal:
    return AccountRepository().get_user_account(user.id, currency).account_balance


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


def _assert_pending_in(deposit, currency: str) -> None:
    """Held for an admin, recorded in the line's currency against RemitX's
    bank account in it, with no balance moved."""
    transaction = TransactionRepository().get_by_id(deposit.tx_id)
    source = AccountRepository().get_by_id(transaction.credit_account_id)
    assert deposit.user_id is None
    assert transaction.status == STATUS_PENDING
    assert transaction.debit_account_id is None
    assert transaction.currency == currency
    assert source.type == TYPE_PLATFORM_FIAT
    assert source.account_currency == currency
    assert source.account_balance == 0


@pytest.mark.parametrize("currency", ["ZAR", " zar "])
def test_matching_zar_reference_confirms_and_credits_immediately(app_context, currency):
    seed_platform_accounts()
    user = _customer("dep")
    zar_reference = f"{user.base_reference}-zar"

    operator = _admin()
    result = deposit_service.process_deposits(
        [
            {
                "reference": zar_reference,
                "amount": "500.00",
                "currency": currency,
                "date": "2026-09-10",
            }
        ],
        actor_user_id=operator.id,
    )

    [deposit] = result.deposits
    assert deposit.user_id == user.id
    _assert_deposited_in(deposit, CURRENCY_ZAR, "500.00")
    (entry,) = db.session.scalars(
        select(AuditLog).where(AuditLog.action == AuditAction.CASHIN_CONFIRMED.value)
    ).all()
    assert entry.actor_user_id == operator.id
    assert entry.subject_id == deposit.deposit_id
    assert entry.after["auto_matched"] is True


@pytest.mark.parametrize("currency", FOREIGN_CURRENCIES)
def test_line_in_a_foreign_currency_credits_that_account(app_context, currency):
    """A USD line quoting the customer's USD reference comes out of RemitX's
    USD bank account, never the ZAR one, and leaves their ZAR balance alone.
    """
    seed_platform_accounts()
    user = _customer("fx_dep", currency)
    reference = create_account_reference(user.base_reference, currency)

    result = deposit_service.process_deposits(
        [
            {
                "reference": reference,
                "amount": "500.00",
                "currency": currency,
                "date": "2026-09-10",
            }
        ]
    )

    [deposit] = result.deposits
    assert deposit.user_id == user.id
    _assert_deposited_in(deposit, currency, "500.00")
    assert _balance(user, CURRENCY_ZAR) == 0
    assert _bank_balance(CURRENCY_ZAR) == 0


@pytest.mark.parametrize(
    ("line_currency", "account_currency"),
    [
        (CURRENCY_ZAR, CURRENCY_USD),
        (CURRENCY_ZAR, CURRENCY_ZWL),
        (CURRENCY_ZAR, CURRENCY_NAD),
        (CURRENCY_ZAR, CURRENCY_TOKEN),
        (CURRENCY_USD, CURRENCY_ZAR),
    ],
)
def test_reference_to_an_account_in_another_currency_is_left_pending(
    app_context, line_currency, account_currency
):
    """R1,000 quoting sipho1-usd is still R1,000. It is never credited as
    $1,000, or as 1,000 tokens: the line waits for an admin, in ZAR."""
    seed_platform_accounts()
    extra = (account_currency,) if account_currency in FOREIGN_CURRENCIES else ()
    user = _customer("mismatch", *extra)
    reference = create_account_reference(user.base_reference, account_currency)

    result = deposit_service.process_deposits(
        [
            {
                "reference": reference,
                "amount": "1000.00",
                "currency": line_currency,
                "date": "2026-09-10",
            }
        ]
    )

    [deposit] = result.deposits
    _assert_pending_in(deposit, line_currency)
    assert deposit_service.get_pending_deposits() == [deposit]
    assert _balance(user, account_currency) == 0
    assert _balance(user, CURRENCY_ZAR) == 0


@pytest.mark.parametrize("currency", [None, "", CURRENCY_TOKEN, "JPY"])
def test_line_without_a_currency_remitx_banks_in_is_skipped(app_context, currency):
    seed_platform_accounts()
    user = _customer("no_currency")
    row = {
        "reference": f"{user.base_reference}-zar",
        "amount": "80.00",
        "date": "2026-09-10",
    }
    if currency is not None:
        row["currency"] = currency

    result = deposit_service.process_deposits([row])

    assert result.deposits == []
    [skipped] = result.skipped
    assert skipped.reason == SkippedStatementLineReason.UNKNOWN_CURRENCY
    assert deposit_service.get_pending_deposits() == []
    assert _balance(user, CURRENCY_ZAR) == 0


def test_two_identical_date_only_lines_in_one_statement_both_credit(app_context):
    """Two genuine same-day deposits with the same reference and amount."""
    seed_platform_accounts()
    user = _customer("double_dep")
    zar_reference = f"{user.base_reference}-zar"
    line = {
        "reference": zar_reference,
        "amount": "500.00",
        "currency": "ZAR",
        "date": "2026-09-10",
    }

    result = deposit_service.process_deposits([line, dict(line)])

    assert len(result.deposits) == 2
    assert result.skipped == []
    assert _balance(user, CURRENCY_ZAR) == Decimal("1000.00")


def test_same_day_deposits_with_distinct_times_both_credit(app_context):
    seed_platform_accounts()
    user = _customer("timed_dep")
    zar_reference = f"{user.base_reference}-zar"

    result = deposit_service.process_deposits(
        [
            {
                "reference": zar_reference,
                "amount": "500.00",
                "currency": "ZAR",
                "date": "2026-09-10T09:15:00",
            },
            {
                "reference": zar_reference,
                "amount": "500.00",
                "currency": "ZAR",
                "date": "2026-09-10T16:45:00",
            },
        ]
    )

    assert len(result.deposits) == 2
    assert _balance(user, CURRENCY_ZAR) == Decimal("1000.00")


def test_statement_line_id_is_the_deduplication_key(app_context):
    seed_platform_accounts()
    user = _customer("line_id")
    zar_reference = f"{user.base_reference}-zar"
    row = {
        "line_id": "BNK-8821",
        "reference": zar_reference,
        "amount": "500.00",
        "currency": "ZAR",
        "date": "2026-09-10",
    }

    first = deposit_service.process_deposits([row])
    second = deposit_service.process_deposits([row])

    assert len(first.deposits) == 1
    assert second.deposits == []
    assert len(second.skipped) == 1
    assert _balance(user, CURRENCY_ZAR) == Decimal("500.00")


def test_reprocessing_the_same_statement_line_does_not_credit_again(app_context):
    """Uploading the same CSV twice, or an overlapping date range, must not
    create a second deposit or move the balance again.
    """
    seed_platform_accounts()
    user = _customer("dedup")
    zar_reference = f"{user.base_reference}-zar"
    line = {
        "reference": zar_reference,
        "amount": "500.00",
        "currency": "ZAR",
        "date": "2026-09-10",
    }

    first = deposit_service.process_deposits([line])
    second = deposit_service.process_deposits([line])

    assert len(first.deposits) == 1
    assert second.deposits == []
    assert len(second.skipped) == 1
    assert _balance(user, CURRENCY_ZAR) == Decimal("500.00")
    assert len(deposit_service.get_deposits_for_user(user.id)) == 1

    later = deposit_service.process_deposits([{**line, "amount": "10.00"}])
    assert len(later.deposits) == 1
    assert _balance(user, CURRENCY_ZAR) == Decimal("510.00")


def test_reprocessing_two_identical_lines_skips_both(app_context):
    seed_platform_accounts()
    user = _customer("dedup_pair")
    zar_reference = f"{user.base_reference}-zar"
    line = {
        "reference": zar_reference,
        "amount": "500.00",
        "currency": "ZAR",
        "date": "2026-09-10",
    }
    pair = [line, dict(line)]

    first = deposit_service.process_deposits(pair)
    second = deposit_service.process_deposits(pair)

    assert len(first.deposits) == 2
    assert second.deposits == []
    assert len(second.skipped) == 2
    assert _balance(user, CURRENCY_ZAR) == Decimal("1000.00")


def test_the_same_line_in_two_currencies_is_two_deposits(app_context):
    """Currency is part of a line's identity: a ZAR line and a USD line with
    the same day, reference and amount are two different payments."""
    seed_platform_accounts()
    user = _customer("two_currencies", CURRENCY_USD)
    line = {
        "reference": f"{user.base_reference}-usd",
        "amount": "100.00",
        "date": "2026-09-10",
    }

    result = deposit_service.process_deposits(
        [{**line, "currency": "ZAR"}, {**line, "currency": "USD"}]
    )

    assert result.skipped == []
    zar_line, usd_line = result.deposits
    _assert_pending_in(zar_line, CURRENCY_ZAR)
    _assert_deposited_in(usd_line, CURRENCY_USD, "100.00")


def test_reprocessing_an_unmatched_line_does_not_queue_it_twice(app_context):
    seed_platform_accounts()
    line = {
        "reference": "not-a-person",
        "amount": "80.00",
        "currency": "ZAR",
        "date": "2026-09-09",
    }

    deposit_service.process_deposits([line])
    again = deposit_service.process_deposits([line])

    assert len(deposit_service.get_pending_deposits()) == 1
    assert len(again.skipped) == 1


@pytest.mark.parametrize("currency", (CURRENCY_ZAR, *FOREIGN_CURRENCIES))
def test_approving_credits_the_account_in_the_deposits_currency(app_context, currency):
    seed_platform_accounts()
    extra = (currency,) if currency in FOREIGN_CURRENCIES else ()
    user = _customer("approve", *extra)
    deposit_service.process_deposits(
        [
            {
                "reference": "not-a-person",
                "amount": "80.00",
                "currency": currency,
                "date": "2026-09-11",
            }
        ]
    )
    [pending] = deposit_service.get_pending_deposits()

    reference = create_account_reference(user.base_reference, currency)
    deposit = deposit_service.approve_pending_deposit(
        pending.deposit_id, reference.upper(), _admin().id
    )

    assert deposit.user_id == user.id
    _assert_deposited_in(deposit, currency, "80.00")
    assert deposit_service.get_pending_deposits() == []


@pytest.mark.parametrize(
    ("deposit_currency", "account_currency"),
    [
        (CURRENCY_ZAR, CURRENCY_USD),
        (CURRENCY_ZAR, CURRENCY_TOKEN),
        (CURRENCY_USD, CURRENCY_ZAR),
    ],
)
def test_approving_with_an_account_in_another_currency_is_refused(
    app_context, deposit_currency, account_currency
):
    """The deposit stays pending and no balance moves."""
    seed_platform_accounts()
    user = _customer("approve_mismatch", CURRENCY_USD)
    deposit_service.process_deposits(
        [
            {
                "reference": "not-a-person",
                "amount": "80.00",
                "currency": deposit_currency,
                "date": "2026-09-11",
            }
        ]
    )
    [pending] = deposit_service.get_pending_deposits()

    with pytest.raises(DepositCurrencyMismatchError):
        deposit_service.approve_pending_deposit(
            pending.deposit_id,
            create_account_reference(user.base_reference, account_currency),
            _admin().id,
        )

    for currency in (CURRENCY_ZAR, CURRENCY_USD, CURRENCY_TOKEN):
        assert _balance(user, currency) == 0
    assert deposit_service.get_pending_deposits() == [pending]
    _assert_pending_in(pending, deposit_currency)


def test_unparseable_statement_date_is_skipped(app_context):
    seed_platform_accounts()

    result = deposit_service.process_deposits(
        [
            {
                "reference": "remitx deposit",
                "amount": "80.00",
                "currency": "ZAR",
                "date": "not-a-date",
            }
        ]
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
    user = _customer("mixed")
    zar_reference = f"{user.base_reference}-zar"

    result = deposit_service.process_deposits(
        [
            {
                "reference": "SALARY-SEP26",
                "amount": "-18500.00",
                "currency": "ZAR",
                "date": "2026-09-08",
            },
            {
                "reference": zar_reference,
                "amount": "500.00",
                "currency": "ZAR",
                "date": "2026-09-10",
            },
        ]
    )

    assert len(result.deposits) == 1
    assert result.deposits[0].user_id == user.id
    assert len(result.skipped) == 1
    assert _balance(user, CURRENCY_ZAR) == Decimal("500.00")
