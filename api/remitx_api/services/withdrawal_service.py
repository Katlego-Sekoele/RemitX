"""Withdrawal request + settlement
Withdrawal is the movement between a user's own fiat bank account and
RemitX's platform fiat account. The net transaction into the platform fiat
account is the (mock) external payout itself — see `_settle_withdrawal`.

The cash-out fee (`Config.CASH_OUT_FEE_RATE`, applied to the gross requested
amount) is deducted from the withdrawn amount and paid into RemitX's fee
revenue account (`REMITX_REVENUE`) for the withdrawal's currency — the same
kind of account a remittance fee lands in — while the net payout transaction
goes to the RemitX fiat bank account in that currency.

The destination bank account must already be `verified`.

Possible evolution: if a real payment-gateway call is ever added to the
payout transaction, settlement should move to the same async pattern
remittance settlement uses.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    TYPE_PLATFORM_FIAT,
    TYPE_PLATFORM_REVENUE,
)
from remitx_api.models.orm.bank_account import (
    STATUS_REJECTED,
    STATUS_VERIFIED,
)
from remitx_api.models.orm.transaction import (
    STATUS_PENDING,
    TYPE_FEE,
    TYPE_WITHDRAWAL,
    Transaction,
)
from remitx_api.models.orm.withdrawal import Withdrawal
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.bank_account_repository import BankAccountRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.withdrawal_repository import WithdrawalRepository
from remitx_api.services.bank_account_service import BankAccountNotFoundError
from remitx_api.services.quote_service import AMOUNT_QUANTUM, round_amount

logger = logging.getLogger(__name__)

CONFIRMED_BY_SYSTEM = "system"


class BankAccountRejectedError(Exception):
    """This bank account was rejected by an admin and can't receive funds."""


class BankAccountNotVerifiedError(Exception):
    """This bank account hasn't been verified by an admin yet, so it can't
    receive a withdrawal. Not expected on the normal path — the withdrawal
    page only ever offers a caller's already-verified accounts."""


class CurrencyMismatchError(Exception):
    """The requested currency isn't withdrawable, has no account for this
    user, or doesn't match the target bank account's own currency."""


class InvalidAmountError(Exception):
    """The requested amount is zero or negative once rounded to 2dp."""


class InsufficientBalanceError(Exception):
    """The caller's available balance can't cover the requested amount."""


class WithdrawalNotPendingError(Exception):
    """Already settled — the guarded transition refused."""


def request_withdrawal(
    user_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    currency: str,
    amount: Decimal,
) -> Withdrawal:
    """Validate, lock the funds, and settle immediately — the destination
    bank account must already be verified (see the module docstring).
    """
    # No withdrawals are allowed from a user's token account.
    if currency == CURRENCY_TOKEN:
        logger.warning(
            "withdrawal refused for user %s: currency=%s is a token balance",
            user_id,
            currency,
        )
        raise CurrencyMismatchError("Cannot withdraw a token balance directly")

    accounts = AccountRepository()
    bank_accounts = BankAccountRepository()
    transactions = TransactionRepository()
    withdrawals = WithdrawalRepository()

    # Get the bank account object by its ID
    bank_account = bank_accounts.get_by_id(bank_account_id)
    if bank_account is None or bank_account.user_id != user_id:
        logger.warning(
            "withdrawal refused for user %s: bank_account %s not found",
            user_id,
            bank_account_id,
        )
        raise BankAccountNotFoundError(str(bank_account_id))
    if bank_account.status == STATUS_REJECTED:
        logger.warning(
            "withdrawal refused for user %s: bank_account %s is rejected",
            user_id,
            bank_account_id,
        )
        raise BankAccountRejectedError(str(bank_account_id))
    if bank_account.status != STATUS_VERIFIED:
        logger.warning(
            "withdrawal refused for user %s: bank_account %s is not verified yet",
            user_id,
            bank_account_id,
        )
        raise BankAccountNotVerifiedError(str(bank_account_id))
    if bank_account.currency != currency:
        logger.warning(
            "withdrawal refused for user %s: bank_account %s is %s, not %s",
            user_id,
            bank_account_id,
            bank_account.currency,
            currency,
        )
        raise CurrencyMismatchError(
            f"Bank account is denominated in {bank_account.currency}, not {currency}"
        )

    # Get the user's platform fiat account in the requested withdrawalcurrency
    user_fiat_account = accounts.get_user_account(user_id, currency)
    if user_fiat_account is None:
        logger.warning(
            "withdrawal refused for user %s: no %s account", user_id, currency
        )
        raise CurrencyMismatchError(f"No {currency} account for this user")

    # Round the requested amount to the nearest valid quantum
    amount = round_amount(amount)
    # Calculate the minimum amount allowed for withdrawal, which is the sum of the
    # minimum cash-out fee and the amount quantum.
    min_amount = Config.MIN_CASH_OUT_FEE + AMOUNT_QUANTUM
    # If the requested amount is less than the minimum allowed amount.
    if amount < min_amount:
        logger.warning(
            "withdrawal refused for user %s: amount %s below minimum", user_id, amount
        )
        raise InvalidAmountError(f"Amount must be at least {min_amount}, got {amount}")
    # get user's available balance in the requested currency and check if it's
    # sufficient for the withdrawal.
    available = accounts.get_available_balance_locked(user_fiat_account.account_id)
    if available < amount:
        logger.warning(
            "withdrawal refused for user %s: available balance %s < requested %s",
            user_id,
            available,
            amount,
        )
        raise InsufficientBalanceError(
            f"available balance {available} is less than {amount}"
        )
    # payout fee calculation.
    fee = max(round_amount(Config.CASH_OUT_FEE_RATE * amount), Config.MIN_CASH_OUT_FEE)
    net = amount - fee  # Amount payable to the user after deducting the fee

    # The fee transaction goes to RemitX's fee revenue account and the net
    # transaction goes to RemitX's fiat platform account, both in the
    # withdrawal's own currency.
    fee_revenue_account = accounts.get_platform_account(TYPE_PLATFORM_REVENUE, currency)
    payout_source_account = accounts.get_platform_account(TYPE_PLATFORM_FIAT, currency)
    # RemitX has no fiat/revenue account seeded in this currency, so it can't
    # pay out in it. A seeding gap, not a customer mistake, hence the error log.
    if fee_revenue_account is None or payout_source_account is None:
        logger.error(
            "withdrawal refused for user %s: no RemitX %s fiat/revenue account",
            user_id,
            currency,
        )
        raise CurrencyMismatchError(f"Withdrawals in {currency} are not available")

    # fee transaction
    fee_tx = transactions.add(
        Transaction(
            type=TYPE_FEE,
            credit_account_id=user_fiat_account.account_id,
            debit_account_id=fee_revenue_account.account_id,
            amount=fee,
            currency=currency,
            status=STATUS_PENDING,
        )
    )
    # Withdrawal transaction (net amount)
    # User fiat account is credited (decreased) and the payout source account is
    # debited (increased).
    withdrawal_tx = transactions.add(
        Transaction(
            type=TYPE_WITHDRAWAL,
            credit_account_id=user_fiat_account.account_id,
            debit_account_id=payout_source_account.account_id,
            amount=net,
            currency=currency,
            status=STATUS_PENDING,
        )
    )
    # Create the withdrawal record linking the transactions and the bank account.
    withdrawal = withdrawals.add(
        Withdrawal(
            tx_id=withdrawal_tx.tx_id,
            fee_tx_id=fee_tx.tx_id,
            user_id=user_id,
            bank_account_id=bank_account_id,
            gross_amount=amount,
            fee_amount=fee,
            net_amount=net,
            currency=currency,
        )
    )
    logger.info(
        "withdrawal %s requested by user %s: amount=%s fee=%s currency=%s "
        "bank_account=%s",
        withdrawal.withdrawal_id,
        user_id,
        amount,
        fee,
        currency,
        bank_account_id,
    )

    # Immediately settle the withdrawal, which confirms the pending transactions
    # and moves the balances. Not committed before this: settlement commits the
    # request and the settlement together, or rolls both back, so a refused
    # settlement can't leave pending transactions holding the customer's funds.
    _settle_withdrawal(withdrawal, confirmed_by=CONFIRMED_BY_SYSTEM)

    return withdrawals.get_by_id(withdrawal.withdrawal_id)


def list_user_withdrawals(user_id: uuid.UUID) -> list[tuple[Withdrawal, Transaction]]:
    """List all withdrawals for a user, with their associated transactions."""
    return WithdrawalRepository().list_user_withdrawals(user_id)


def _settle_withdrawal(withdrawal: Withdrawal, confirmed_by: str) -> None:
    """Confirm the withdrawal's pending transactions and move the balances. Raises
    `WithdrawalNotPendingError` if the transactions aren't `pending` any more
    (already settled), after rolling back everything uncommitted in the
    session — including, when called from `request_withdrawal`, the withdrawal
    row and its transactions."""
    accounts = AccountRepository()
    transactions = TransactionRepository()

    confirmed_at = datetime.now(UTC)
    # Confirm the pending transactions for the withdrawal.
    if not transactions.confirm_pending_transactions(
        [withdrawal.fee_tx_id, withdrawal.tx_id], confirmed_at
    ):
        withdrawal_id = withdrawal.withdrawal_id
        logger.error(
            "withdrawal %s settlement refused: fee transaction %s / "
            "withdrawal transaction %s no longer pending",
            withdrawal_id,
            withdrawal.fee_tx_id,
            withdrawal.tx_id,
        )
        db.session.rollback()
        raise WithdrawalNotPendingError(str(withdrawal_id))

    # get the user's fiat account in the withdrawal's currency
    user_fiat_account = accounts.get_user_account(
        withdrawal.user_id, withdrawal.currency
    )
    # Decrease the user's fiat account balance by the gross withdrawal amount
    # (which includes the fee)
    accounts.decrease_balance(user_fiat_account.account_id, withdrawal.gross_amount)

    fee_revenue_account = accounts.get_platform_account(
        TYPE_PLATFORM_REVENUE, withdrawal.currency
    )
    # Increase the fee revenue account balance by the fee amount
    accounts.increase_balance(fee_revenue_account.account_id, withdrawal.fee_amount)
    payout_account = accounts.get_platform_account(
        TYPE_PLATFORM_FIAT, withdrawal.currency
    )
    # Increase the payout source account balance by the net amount. This
    # transaction is the external payout: REMITX_FIAT's balance is the negative
    # of the cash RemitX holds (a deposit took it below zero), so moving it back
    # towards zero is the net leaving RemitX's bank for the user's real bank
    # account.
    accounts.increase_balance(payout_account.account_id, withdrawal.net_amount)

    # Settlement runs once per withdrawal.
    withdrawal.confirmed_by = confirmed_by
    logger.info(
        "withdrawal %s settled: user=%s amount=%s fee=%s currency=%s confirmed_by=%s",
        withdrawal.withdrawal_id,
        withdrawal.user_id,
        withdrawal.gross_amount,
        withdrawal.fee_amount,
        withdrawal.currency,
        confirmed_by,
    )

    db.session.commit()  # Commit changes
