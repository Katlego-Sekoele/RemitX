"""Withdrawal request + settlement: the fiat-account-to-bank leg described in
Transaction_Flow_Context.md §2 Phase E, adapted.

That section's text is stale: it assumes a resting `uctusd` balance gets
burned at withdrawal time, but §2 Phase C now auto-converts and burns at
remittance-settlement time instead (see remittance_service.py), so by the
time anyone withdraws they're already holding real fiat. Nothing here
touches XRPL or the token ledger — this is a pure ledger movement between a
user's own fiat account and RemitX's platform fiat account, plus a mock
external payout.

The cash-out fee (`Config.CASH_OUT_FEE_RATE`, applied to the gross requested
amount) is deducted from the withdrawn amount and paid into that same
RemitX fiat bank account — the one denominated in the receiver's own
currency — rather than a separate revenue account, so it settles alongside
the net payout leg in one balance movement.

The destination bank account must already be `verified`
(models/orm/bank_account.py) — `request_withdrawal` refuses outright
otherwise (`BankAccountNotVerifiedError`/`BankAccountRejectedError`), never
parking the legs as a `pending` hold waiting on an admin. The frontend's
withdrawal page only ever offers a caller's verified accounts as
destinations (`GET /bank-accounts/withdrawable`), so in the normal flow this
can't happen; the check exists for a direct API call or a bank account that
gets rejected in the gap between the picker loading and the request landing.
A verified account always settles immediately, synchronously, in the same
call — no queue, no worker, no admin step, just a sequential chain of
function calls, same as `deposit_service.approve_pending_deposit`.

Possible evolution: if a real payment-gateway call is ever added to the
payout leg, settlement should move to the same async pattern remittance
settlement uses (queue_service + a worker task claiming `pending` rows)
rather than staying inline on the request thread.
"""

import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from remitx_api.config import Config
from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_TOKEN, TYPE_PLATFORM_FIAT
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

    Locking happens the same way a deposit's or remittance's pending leg
    does: inserting a `pending` transaction never touches `account_balance`
    directly, but `AccountRepository.get_available_balance` subtracts every
    pending/processing outgoing leg from it — so the funds are unavailable
    to a second withdrawal the instant this commits, whether or not
    settlement follows immediately. The balance check itself uses the
    row-locking `get_available_balance_locked` rather than the plain
    version, closing the check-then-insert race a second concurrent
    request against the same account (another withdrawal, or a remittance
    confirm) would otherwise be able to slip through before this one's
    `pending` leg commits.
    """
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

    fiat_account = accounts.get_user_account(user_id, currency)
    if fiat_account is None:
        logger.warning(
            "withdrawal refused for user %s: no %s account", user_id, currency
        )
        raise CurrencyMismatchError(f"No {currency} account for this user")

    amount = round_amount(amount)
    # Every withdrawal carries a fee leg of at least Config.MIN_CASH_OUT_FEE,
    # so the smallest withdrawal is one cent more than that, leaving a
    # non-zero net payout. A negative amount would reverse both legs and
    # *credit* the user.
    min_amount = Config.MIN_CASH_OUT_FEE + AMOUNT_QUANTUM
    if amount < min_amount:
        logger.warning(
            "withdrawal refused for user %s: amount %s below minimum", user_id, amount
        )
        raise InvalidAmountError(f"Amount must be at least {min_amount}, got {amount}")
    available = accounts.get_available_balance_locked(fiat_account.account_id)
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

    fee = max(round_amount(Config.CASH_OUT_FEE_RATE * amount), Config.MIN_CASH_OUT_FEE)
    net = amount - fee

    # Both legs land in the same RemitX fiat bank account for this currency
    # — the fee isn't split off into a separate revenue account here, it's
    # paid straight into the same account the net payout leg uses.
    payout_source_account = accounts.get_platform_account(TYPE_PLATFORM_FIAT, currency)

    fee_tx = transactions.add(
        Transaction(
            type=TYPE_FEE,
            credit_account_id=fiat_account.account_id,
            debit_account_id=payout_source_account.account_id,
            amount=fee,
            currency=currency,
            status=STATUS_PENDING,
        )
    )

    withdrawal_tx = transactions.add(
        Transaction(
            type=TYPE_WITHDRAWAL,
            credit_account_id=fiat_account.account_id,
            debit_account_id=payout_source_account.account_id,
            amount=net,
            currency=currency,
            status=STATUS_PENDING,
        )
    )

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
    db.session.commit()
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

    _settle_withdrawal(withdrawal, confirmed_by=CONFIRMED_BY_SYSTEM)

    return withdrawals.get_by_id(withdrawal.withdrawal_id)


def list_user_withdrawals(user_id: uuid.UUID) -> list[tuple[Withdrawal, Transaction]]:
    return WithdrawalRepository().list_user_withdrawals(user_id)


def _settle_withdrawal(withdrawal: Withdrawal, confirmed_by: str) -> None:
    """Confirm the withdrawal's pending leg(s) and move the balances. Raises
    `WithdrawalNotPendingError` if the legs aren't `pending` any more
    (already settled)."""
    accounts = AccountRepository()
    transactions = TransactionRepository()

    confirmed_at = datetime.now(UTC)
    if not transactions.confirm_pending_transaction(withdrawal.fee_tx_id, confirmed_at):
        logger.error(
            "withdrawal %s settlement refused: fee leg %s is no longer pending",
            withdrawal.withdrawal_id,
            withdrawal.fee_tx_id,
        )
        raise WithdrawalNotPendingError(str(withdrawal.withdrawal_id))
    if not transactions.confirm_pending_transaction(withdrawal.tx_id, confirmed_at):
        logger.error(
            "withdrawal %s settlement refused: leg %s is no longer pending",
            withdrawal.withdrawal_id,
            withdrawal.tx_id,
        )
        raise WithdrawalNotPendingError(str(withdrawal.withdrawal_id))

    fiat_account = accounts.get_user_account(withdrawal.user_id, withdrawal.currency)
    accounts.decrease_balance(fiat_account.account_id, withdrawal.gross_amount)
    # Both the fee leg and the net leg credit the same RemitX fiat account
    # (see request_withdrawal), so the gross amount moves there in one call.
    payout_account = accounts.get_platform_account(
        TYPE_PLATFORM_FIAT, withdrawal.currency
    )
    accounts.increase_balance(payout_account.account_id, withdrawal.gross_amount)

    # Settlement runs once per withdrawal (guarded by the pending -> confirmed
    # legs above) and commits with them, so a plain assignment is enough.
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

    db.session.commit()
