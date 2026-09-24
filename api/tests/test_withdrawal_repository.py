"""Repository-level tests for the withdrawal ledger pieces: the guarded
transitions `request_withdrawal`/`_settle_withdrawal` rely on to stop a
double settle, and the locked available-balance read."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from remitx_api.controllers.user_controller import UserController
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, TYPE_PLATFORM_FIAT, Account
from remitx_api.models.orm.bank_account import BankAccount
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_FAILED,
    STATUS_PENDING,
    TYPE_FEE,
    TYPE_WITHDRAWAL,
    Transaction,
)
from remitx_api.models.orm.withdrawal import Withdrawal
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.withdrawal_repository import WithdrawalRepository


def _setup(balance="1000"):
    user = UserController().ensure_provisioned(
        "user_wd_repo", lambda: "wd-repo@example.com", lambda: "Repo"
    )
    platform = Account(
        user_id=None,
        type=TYPE_PLATFORM_FIAT,
        account_currency=CURRENCY_ZAR,
        label="RemitX SA Bank Account",
    )
    db.session.add(platform)
    bank_account = BankAccount(
        user_id=user.id,
        account_holder_name="Repo",
        bank_name="FNB",
        account_number="123456",
        currency=CURRENCY_ZAR,
    )
    db.session.add(bank_account)
    db.session.commit()
    accounts = AccountRepository()
    zar = accounts.get_user_account(user.id, CURRENCY_ZAR)
    accounts.increase_balance(zar.account_id, Decimal(balance))
    db.session.commit()
    return user, zar, platform, bank_account


def _pending_tx(
    zar, platform, amount, created_at=None, type_=TYPE_WITHDRAWAL
) -> Transaction:
    tx = Transaction(
        type=type_,
        credit_account_id=zar.account_id,
        debit_account_id=platform.account_id,
        amount=Decimal(amount),
        currency=CURRENCY_ZAR,
        status=STATUS_PENDING,
    )
    if created_at is not None:
        tx.created_at = created_at
    return TransactionRepository().add(tx)


def _withdrawal(user, bank_account, tx, fee_tx, amount="100") -> Withdrawal:
    return WithdrawalRepository().add(
        Withdrawal(
            tx_id=tx.tx_id,
            fee_tx_id=fee_tx.tx_id,
            user_id=user.id,
            bank_account_id=bank_account.bank_account_id,
            gross_amount=Decimal(amount),
            fee_amount=fee_tx.amount,
            net_amount=Decimal(amount) - fee_tx.amount,
            currency=CURRENCY_ZAR,
        )
    )


def test_confirm_pending_transaction_is_one_shot(app_context):
    _, zar, platform, _ = _setup()
    tx = _pending_tx(zar, platform, "10")
    transactions = TransactionRepository()
    now = datetime.now(UTC)

    assert transactions.confirm_pending_transaction(tx.tx_id, now) is True
    assert transactions.confirm_pending_transaction(tx.tx_id, now) is False
    db.session.refresh(tx)
    assert tx.status == STATUS_CONFIRMED
    assert tx.confirmed_at is not None
    assert tx.processed_at is not None


def test_confirm_pending_transactions_is_all_or_nothing(app_context):
    _, zar, platform, _ = _setup()
    first = _pending_tx(zar, platform, "10")
    second = _pending_tx(zar, platform, "10")
    transactions = TransactionRepository()
    now = datetime.now(UTC)

    assert (
        transactions.confirm_pending_transactions([first.tx_id, second.tx_id], now)
        is True
    )
    db.session.commit()
    # Both already confirmed: a second attempt changes nothing.
    assert (
        transactions.confirm_pending_transactions([first.tx_id, second.tx_id], now)
        is False
    )

    # One pending, one not: reports False even though it confirmed the
    # pending one, which is why the caller rolls back.
    third = _pending_tx(zar, platform, "10")
    db.session.commit()
    assert (
        transactions.confirm_pending_transactions([first.tx_id, third.tx_id], now)
        is False
    )
    db.session.rollback()
    db.session.refresh(third)
    assert third.status == STATUS_PENDING


def test_fail_pending_transaction_only_fails_pending_rows(app_context):
    _, zar, platform, _ = _setup()
    pending = _pending_tx(zar, platform, "10")
    confirmed = _pending_tx(zar, platform, "10")
    transactions = TransactionRepository()
    transactions.confirm_pending_transaction(confirmed.tx_id, datetime.now(UTC))

    assert transactions.fail_pending_transaction(pending.tx_id) is True
    assert transactions.fail_pending_transaction(pending.tx_id) is False
    assert transactions.fail_pending_transaction(confirmed.tx_id) is False
    db.session.refresh(pending)
    db.session.refresh(confirmed)
    assert pending.status == STATUS_FAILED
    assert confirmed.status == STATUS_CONFIRMED


def test_confirm_or_fail_unknown_transaction_is_false(app_context):
    transactions = TransactionRepository()

    assert (
        transactions.confirm_pending_transaction(uuid.uuid4(), datetime.now(UTC))
        is False
    )
    assert transactions.fail_pending_transaction(uuid.uuid4()) is False


def test_list_user_withdrawals_is_newest_first_and_scoped_to_user(app_context):
    user, zar, platform, bank_account = _setup()
    base = datetime.now(UTC)
    older_at = base - timedelta(hours=1)
    older = _withdrawal(
        user,
        bank_account,
        _pending_tx(zar, platform, "1", older_at),
        _pending_tx(zar, platform, "0.01", older_at, type_=TYPE_FEE),
    )
    newer = _withdrawal(
        user,
        bank_account,
        _pending_tx(zar, platform, "2", base),
        _pending_tx(zar, platform, "0.01", base, type_=TYPE_FEE),
    )
    db.session.commit()

    listed = WithdrawalRepository().list_user_withdrawals(user.id)

    assert [w.withdrawal_id for w, _ in listed] == [
        newer.withdrawal_id,
        older.withdrawal_id,
    ]
    # Each withdrawal is paired with its own withdrawal leg, not the fee leg.
    assert all(tx.tx_id == w.tx_id for w, tx in listed)
    assert WithdrawalRepository().list_user_withdrawals(uuid.uuid4()) == []


def test_locked_available_balance_subtracts_in_flight_outgoing_legs(app_context):
    _, zar, platform, _ = _setup("1000")
    _pending_tx(zar, platform, "300")
    confirmed = _pending_tx(zar, platform, "50")
    TransactionRepository().confirm_pending_transaction(
        confirmed.tx_id, datetime.now(UTC)
    )
    db.session.commit()
    accounts = AccountRepository()

    locked = accounts.get_available_balance_locked(zar.account_id)

    # The confirmed leg's balance move hasn't been applied here (the service
    # does that), so only the still-pending 300 is subtracted.
    assert locked == Decimal("700")
    assert locked == accounts.get_available_balance(zar.account_id)
