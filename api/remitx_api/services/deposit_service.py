import csv
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError

from remitx_api.errors.deposits import (
    DepositNotPendingError,
    PlatformBankAccountMissingError,
    TokenAccountDepositError,
    UnknownDepositReferenceError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    CURRENCY_TOKEN,
    CURRENCY_ZAR,
    TYPE_PLATFORM_FIAT,
    Account,
)
from remitx_api.models.orm.deposit import CONFIRMED_BY_SYSTEM, Deposit
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    TYPE_DEPOSIT,
    Transaction,
)
from remitx_api.models.schemas.deposit import SkippedStatementLineReason
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.deposit_repository import DepositRepository
from remitx_api.repositories.transaction_repository import TransactionRepository

logger = logging.getLogger(__name__)

# The bank account whose statement is reconciled. A line no reference matches
# is recorded against it, in ZAR, until an admin names the account it
# belongs to.
REMITX_SA_BANK_ACCOUNT_LABEL = "RemitX SA Bank Account"
_AMOUNT_QUANTUM = Decimal("0.01")

_SKIP_MESSAGES: dict[SkippedStatementLineReason, str] = {
    SkippedStatementLineReason.UNPARSEABLE_DATE: (
        "Could not parse the date. Fix it (ISO 8601, e.g. 2026-09-10) and "
        "upload the statement again — nothing was recorded for this line."
    ),
    SkippedStatementLineReason.NOT_INCOMING: (
        "This line is not incoming money (amount must be positive). It was not "
        "recorded as a deposit."
    ),
    SkippedStatementLineReason.ALREADY_RECONCILED: (
        "This line was already reconciled on a previous run and was not credited again."
    ),
}


@dataclass(frozen=True)
class SkippedStatementLine:
    reference: str | None
    amount: Decimal
    date: str | None
    reason: SkippedStatementLineReason

    @property
    def message(self) -> str:
        return _SKIP_MESSAGES[self.reason]


@dataclass(frozen=True)
class ProcessDepositsResult:
    deposits: list[Deposit]
    skipped: list[SkippedStatementLine]


def statement_fingerprint(row: dict, *, statement_date: datetime) -> str:
    """Stable identity of one bank-statement line.

    UTC calendar day of the line (same instant used for the transaction's
    ``created_at``), the reference as written, and the amount at 2dp. The
    same CSV uploaded twice, or an overlapping date range, produces the same
    fingerprint and is not credited again.
    """
    reference = (row.get("reference") or "").strip()
    amount = Decimal(str(row.get("amount"))).quantize(
        _AMOUNT_QUANTUM, rounding=ROUND_HALF_UP
    )
    calendar_day = statement_date.astimezone(UTC).date().isoformat()
    return f"{calendar_day}|{reference}|{format(amount, 'f')}"


def _try_parse_statement_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _statement_date_cell(row: dict) -> str | None:
    raw_date = row.get("date")
    if raw_date in (None, ""):
        return None
    return str(raw_date)


def _skipped_line(
    row: dict,
    *,
    reference: str | None,
    amount: Decimal,
    reason: SkippedStatementLineReason,
) -> SkippedStatementLine:
    return SkippedStatementLine(
        reference=reference,
        amount=amount,
        date=_statement_date_cell(row),
        reason=reason,
    )


def process_deposits(bank_statement: str | list[dict]) -> ProcessDepositsResult:
    """The daily reconciliation job — simulated for this project through the
    admin pushing a button on the admin portal page that executes the job.
    """
    deposit_repo = DepositRepository()
    transaction_repo = TransactionRepository()
    account_repo = AccountRepository()

    touched: list[Deposit] = []
    skipped: list[SkippedStatementLine] = []
    for row in _read_bank_statement(bank_statement):
        deposit, skip = _create_deposit(
            row, deposit_repo, transaction_repo, account_repo
        )
        if deposit is not None:
            touched.append(deposit)
        elif skip is not None:
            skipped.append(skip)

    # Anything that didn't match a user lands as a pending transaction and
    # stays that way — no automatic retry. get_pending_deposits() is what the
    # admin portal calls to list them for manual review, and
    # approve_pending_deposit() is what it calls once an admin has picked
    # the right user for one.
    db.session.commit()
    return ProcessDepositsResult(deposits=touched, skipped=skipped)


def _create_deposit(
    row: dict,
    deposit_repo: DepositRepository,
    transaction_repo: TransactionRepository,
    account_repo: AccountRepository,
) -> tuple[Deposit | None, SkippedStatementLine | None]:
    """Match one bank statement line to an account and write its deposit + transaction.

    - Matched: transaction inserted `confirmed`, crediting the account
      immediately.
    - Unmatched: transaction inserted `pending` with no destination account
      yet, keeping the statement's own reference so an admin can resolve it
      manually — see `get_pending_deposits` / `approve_pending_deposit`.
    - Not incoming money at all (amount <= 0): returns None without writing
      anything. A real bank statement mixes RemitX's own outgoing payments in
      with sender deposits, and `transactions.amount` is never negative
      (§1) — those lines aren't deposits and were never going to become one.

    `row`'s "date" becomes the transaction's `created_at` — see `_parse_statement_date`.
    """
    reference = (row.get("reference") or "").strip() or None
    amount = Decimal(str(row.get("amount")))
    if amount <= 0:
        logger.info(
            "Skipping non-deposit line (reference=%s, amount=%s): not incoming money",
            reference,
            amount,
        )
        return None, _skipped_line(
            row,
            reference=reference,
            amount=amount,
            reason=SkippedStatementLineReason.NOT_INCOMING,
        )

    processed_at = datetime.now(UTC)
    raw_date = row.get("date")
    if raw_date not in (None, "") and _try_parse_statement_datetime(raw_date) is None:
        logger.warning(
            "Skipping statement line with unparseable date (reference=%s, date=%r)",
            reference,
            raw_date,
        )
        return None, _skipped_line(
            row,
            reference=reference,
            amount=amount,
            reason=SkippedStatementLineReason.UNPARSEABLE_DATE,
        )
    statement_date = _parse_statement_date(raw_date, processed_at)
    fingerprint = statement_fingerprint(
        {**row, "reference": reference, "amount": amount},
        statement_date=statement_date,
    )
    if deposit_repo.get_by_statement_fingerprint(fingerprint) is not None:
        logger.info("Skipping statement line already reconciled (%s)", fingerprint)
        return None, _skipped_line(
            row,
            reference=reference,
            amount=amount,
            reason=SkippedStatementLineReason.ALREADY_RECONCILED,
        )

    remitx_bank_account = account_repo.get_platform_account_by_label(
        REMITX_SA_BANK_ACCOUNT_LABEL
    )
    if remitx_bank_account is None:
        raise PlatformBankAccountMissingError(CURRENCY_ZAR)

    try:
        with db.session.begin_nested():
            return (
                _insert_deposit(
                    reference,
                    amount,
                    fingerprint,
                    statement_date,
                    processed_at,
                    remitx_bank_account,
                    deposit_repo,
                    transaction_repo,
                    account_repo,
                ),
                None,
            )
    except IntegrityError:
        # A concurrent reconciliation inserted this fingerprint first.
        logger.info("Skipping statement line already reconciled (%s)", fingerprint)
        return None, _skipped_line(
            row,
            reference=reference,
            amount=amount,
            reason=SkippedStatementLineReason.ALREADY_RECONCILED,
        )


def _insert_deposit(
    reference: str | None,
    amount: Decimal,
    fingerprint: str,
    statement_date: datetime,
    processed_at: datetime,
    remitx_bank_account: Account,
    deposit_repo: DepositRepository,
    transaction_repo: TransactionRepository,
    account_repo: AccountRepository,
) -> Deposit:
    account = _find_account(reference, account_repo)
    # If no account matches the reference, create a pending transaction and deposit
    if account is None:
        logger.info(
            "No deposit account for reference %s (amount=%s): recording as pending",
            reference,
            amount,
        )
        transaction = transaction_repo.add(
            Transaction(
                type=TYPE_DEPOSIT,
                credit_account_id=remitx_bank_account.account_id,
                debit_account_id=None,
                amount=amount,
                currency=remitx_bank_account.account_currency,
                status=STATUS_PENDING,
                created_at=statement_date,
                processed_at=processed_at,
            )
        )
        return deposit_repo.add(
            Deposit(
                tx_id=transaction.tx_id,
                user_account_reference=reference,
                statement_fingerprint=fingerprint,
            )
        )

    # Else we have a user account, so create a confirmed transaction and
    # deposit in that account's currency, out of RemitX's bank account in it.
    source = _bank_account(account.account_currency, account_repo)
    transaction = transaction_repo.add(
        Transaction(
            type=TYPE_DEPOSIT,
            credit_account_id=source.account_id,
            debit_account_id=account.account_id,
            amount=amount,
            currency=account.account_currency,
            status=STATUS_CONFIRMED,
            created_at=statement_date,
            processed_at=processed_at,
            confirmed_at=processed_at,
        )
    )
    account_repo.decrease_balance(source.account_id, amount)
    account_repo.increase_balance(account.account_id, amount)
    return deposit_repo.add(
        Deposit(
            tx_id=transaction.tx_id,
            user_id=account.user_id,
            user_account_reference=reference,
            confirmed_by=CONFIRMED_BY_SYSTEM,
            statement_fingerprint=fingerprint,
        )
    )


def _parse_statement_date(value, processed_at: datetime) -> datetime:
    """The date the bank statement recorded for this line — becomes the
    transaction's `created_at` (rather than "when the row was inserted"),
    so a deposit is ordered, and reported on, by when the money actually
    moved.

    Falls back to `processed_at` when the row didn't carry a date.
    """
    parsed = _try_parse_statement_datetime(value)
    return parsed if parsed is not None else processed_at


def _find_account(
    reference: str | None, account_repo: AccountRepository
) -> Account | None:
    """The account a bank-statement deposit reference names, if a deposit may
    land on it. Any fiat account may. The token account may not, so a line
    quoting a token reference waits for an admin like any unmatched line.
    """
    if not reference:
        return None
    account = account_repo.get_user_account_by_reference(reference)
    if account is None or account.account_currency == CURRENCY_TOKEN:
        return None
    return account


def _bank_account(currency: str, account_repo: AccountRepository) -> Account:
    """RemitX's bank account in `currency`: where a deposit in that currency
    comes in, and so the source leg of its transaction."""
    bank_account = account_repo.get_platform_account(TYPE_PLATFORM_FIAT, currency)
    if bank_account is None:
        raise PlatformBankAccountMissingError(currency)
    return bank_account


def _read_bank_statement(bank_statement: str | list[dict]) -> list[dict]:
    """Normalize a CSV path or an already-parsed list of rows into rows."""
    if isinstance(bank_statement, list):
        return bank_statement
    with open(bank_statement, newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def get_deposit(deposit_id: uuid.UUID) -> Deposit | None:
    """Get a deposit from the database by its ID."""
    return DepositRepository().get_by_id(deposit_id)


def get_deposits_for_user(user_id: uuid.UUID) -> list[Deposit]:
    """Get all deposits from the database for a user. No matter the account"""
    return DepositRepository().list_user_deposits(user_id)


def get_pending_deposits() -> list[Deposit]:
    """Deposits still unmatched to a user, for the admin portal to list and
    let an admin manually resolve — see `approve_pending_deposit`."""
    return DepositRepository().list_pending_deposits()


def approve_pending_deposit(
    deposit_id: uuid.UUID, account_reference: str, admin_id: uuid.UUID
) -> Deposit:
    """An admin manually links a pending deposit to a customer and confirms it.

    The admin-triggered counterpart to automatic matching in
    `_create_deposit` — used when a bank statement line's reference didn't
    match anyone at import time (e.g. a typo, or an unregistered sender) and
    an admin has since worked out which customer it belongs to. They name the
    account by its reference (``sipho1-zar``, ``sipho1-usd``, …). The credit
    lands on that account, in its currency, out of RemitX's bank account in
    the same currency. A token reference is refused: no deposit lands on a
    token account.

    Raises if the deposit isn't pending (already confirmed, or doesn't exist)
    — the guarded transition on its transaction is what stops two admins from
    both confirming the same deposit.
    """
    deposit_repo = DepositRepository()
    transaction_repo = TransactionRepository()
    account_repo = AccountRepository()

    deposit = deposit_repo.get_by_id(deposit_id)
    if deposit is None:
        raise DepositNotPendingError()
    transaction = transaction_repo.get_by_id(deposit.tx_id)

    reference = account_reference.strip().lower()
    matched = account_repo.get_user_account_by_reference(reference)
    if matched is None:
        raise UnknownDepositReferenceError()
    if matched.account_currency == CURRENCY_TOKEN:
        raise TokenAccountDepositError()
    source = _bank_account(matched.account_currency, account_repo)

    confirmed_at = datetime.now(UTC)
    if not transaction_repo.confirm_pending_deposit_transaction(
        deposit.tx_id,
        credit_account_id=source.account_id,
        debit_account_id=matched.account_id,
        currency=matched.account_currency,
        confirmed_at=confirmed_at,
    ):
        raise DepositNotPendingError()

    account_repo.decrease_balance(source.account_id, transaction.amount)
    account_repo.increase_balance(matched.account_id, transaction.amount)
    deposit_repo.link_deposit_to_user(deposit_id, matched.user_id, str(admin_id))

    db.session.commit()
    return deposit_repo.get_by_id(deposit_id)
