import csv
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError

from remitx_api.errors.deposits import (
    DepositCurrencyMismatchError,
    DepositNotPendingError,
    PlatformBankAccountMissingError,
    UnknownDepositReferenceError,
)
from remitx_api.extensions import db
from remitx_api.models.orm.account import (
    PAYOUT_CURRENCIES,
    TYPE_PLATFORM_FIAT,
    Account,
)
from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
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

# RemitX holds one bank account per fiat currency (platform_account_seed.py),
# so a statement line can be in any of them. Never the token.
STATEMENT_CURRENCIES = PAYOUT_CURRENCIES
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
    SkippedStatementLineReason.UNKNOWN_CURRENCY: (
        "The currency is missing or is not one RemitX banks in (ZAR, USD, ZWL "
        "or NAD). Fix it and upload the statement again — nothing was "
        "recorded for this line."
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


def _statement_date_cell_is_date_only(raw_date) -> bool:
    """Whether the CSV cell carries a calendar date only (no time of day)."""
    if raw_date in (None, ""):
        return False
    cell = str(raw_date).strip()
    return len(cell) == 10 and cell[4] == "-" and cell[7] == "-"


def _fingerprint_time_key(raw_date, statement_date: datetime) -> str:
    """The time component of a line's deduplication key.

    A date-only cell is keyed by the calendar date as written, not by
    `statement_date` — that datetime now carries a time of day (see
    `_localize_statement_datetime`) that varies with when reconciliation
    ran, so deriving the key from it would make the same statement line
    fingerprint differently across runs.
    """
    if _statement_date_cell_is_date_only(raw_date):
        return str(raw_date).strip()
    return statement_date.astimezone(UTC).replace(microsecond=0).isoformat()


def statement_line_dedup_base(
    row: dict,
    *,
    reference: str | None,
    amount: Decimal,
    currency: str,
    statement_date: datetime,
    raw_date,
) -> str:
    """Shared prefix for lines that need an occurrence index within one upload."""
    line_id = (row.get("line_id") or "").strip()
    if line_id:
        return f"id:{line_id}|{currency}"
    time_key = _fingerprint_time_key(raw_date, statement_date)
    ref = reference or ""
    quantized = amount.quantize(_AMOUNT_QUANTUM, rounding=ROUND_HALF_UP)
    return f"{time_key}|{ref}|{format(quantized, 'f')}|{currency}"


def statement_fingerprint(
    row: dict,
    *,
    reference: str | None,
    amount: Decimal,
    currency: str,
    statement_date: datetime,
    raw_date,
    occurrence: int,
) -> str:
    """Stable identity of one bank-statement line.

    When the bank export carries a ``line_id``, that id (scoped to currency)
    is the key. Otherwise the UTC instant or calendar date (when the CSV cell
    is date-only), reference, amount at 2dp, currency, and the line's
    occurrence among identical rows in the same upload. Re-uploading the same
    statement produces the same fingerprints and does not credit again.
    """
    line_id = (row.get("line_id") or "").strip()
    if line_id:
        return statement_line_dedup_base(
            row,
            reference=reference,
            amount=amount,
            currency=currency,
            statement_date=statement_date,
            raw_date=raw_date,
        )
    base = statement_line_dedup_base(
        row,
        reference=reference,
        amount=amount,
        currency=currency,
        statement_date=statement_date,
        raw_date=raw_date,
    )
    return f"{base}|#{occurrence}"


def _statement_currency(row: dict) -> str | None:
    """The line's currency, if RemitX has a bank account in it."""
    currency = (row.get("currency") or "").strip().upper()
    return currency if currency in STATEMENT_CURRENCIES else None


def _try_parse_statement_datetime(
    value, processed_at: datetime
) -> datetime | None:
    """Parse a statement date cell to a timezone-aware UTC datetime, or None
    if it can't be parsed.

    A date-only cell (e.g. "2026-09-10") doesn't report a time of day, so
    rather than defaulting to a fabricated midnight, it's timed at
    `processed_at` — the moment reconciliation actually ran.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed
    if _statement_date_cell_is_date_only(value):
        return processed_at
    return parsed.replace(tzinfo=UTC)


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


def process_deposits(
    bank_statement: str | list[dict],
    *,
    actor_user_id: uuid.UUID | None = None,
) -> ProcessDepositsResult:
    """The daily reconciliation job — simulated for this project through the
    admin pushing a button on the admin portal page that executes the job.

    When ``actor_user_id`` is set, each line that auto-matches a customer
    writes a ``cashin.confirmed`` audit entry for that staff member. Callers
    that invoke the job without a human (some tests) omit it.
    """
    deposit_repo = DepositRepository()
    transaction_repo = TransactionRepository()
    account_repo = AccountRepository()

    touched: list[Deposit] = []
    skipped: list[SkippedStatementLine] = []
    occurrence_next: dict[str, int] = defaultdict(int)
    for row in _read_bank_statement(bank_statement):
        reference = (row.get("reference") or "").strip() or None
        try:
            deposit, skip = _create_deposit(
            row,
            deposit_repo,
            transaction_repo,
            account_repo,
            occurrence_next,
            actor_user_id=actor_user_id,
            )
        except Exception:
            logger.error(
                "Failed to process statement line (reference=%s, "
                "currency=%s): unexpected error",
                reference,
                row.get("currency"),
                exc_info=True,
            )
            raise
        
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
    occurrence_next: dict[str, int],
    *,
    actor_user_id: uuid.UUID | None = None,
) -> tuple[Deposit | None, SkippedStatementLine | None]:
    """Match one bank statement line to an account and write its deposit + transaction.

    The line's currency is that of the RemitX bank account it came into, and
    the transaction is recorded in it, out of that bank account.

    - Matched: the reference names the customer's account in the line's
      currency. Transaction inserted `confirmed`, crediting the account
      immediately.
    - Unmatched: no such account, including a reference to one of the
      customer's other currencies or their token account. Transaction
      inserted `pending` with no destination account yet, keeping the
      statement's own reference so an admin can resolve it manually — see
      `get_pending_deposits` / `approve_pending_deposit`.
    - No currency, or one RemitX doesn't bank in: skipped, nothing written.
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
    if (
        raw_date not in (None, "")
        and _try_parse_statement_datetime(raw_date, processed_at) is None
    ):
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
    currency = _statement_currency(row)
    if currency is None:
        logger.warning(
            "Skipping statement line with unknown currency (reference=%s, currency=%r)",
            reference,
            row.get("currency"),
        )
        return None, _skipped_line(
            row,
            reference=reference,
            amount=amount,
            reason=SkippedStatementLineReason.UNKNOWN_CURRENCY,
        )
    statement_date = _parse_statement_date(raw_date, processed_at)
    dedup_base = statement_line_dedup_base(
        row,
        reference=reference,
        amount=amount,
        currency=currency,
        statement_date=statement_date,
        raw_date=raw_date,
    )
    occurrence = occurrence_next[dedup_base]
    occurrence_next[dedup_base] += 1
    fingerprint = statement_fingerprint(
        row,
        reference=reference,
        amount=amount,
        currency=currency,
        statement_date=statement_date,
        raw_date=raw_date,
        occurrence=occurrence,
    )
    if deposit_repo.get_by_statement_fingerprint(fingerprint) is not None:
        logger.info("Skipping statement line already reconciled (%s)", fingerprint)
        return None, _skipped_line(
            row,
            reference=reference,
            amount=amount,
            reason=SkippedStatementLineReason.ALREADY_RECONCILED,
        )

    remitx_bank_account = _bank_account(currency, account_repo)

    try:
        with db.session.begin_nested():
            return (
                _insert_deposit(
                    reference,
                    amount,
                    currency,
                    fingerprint,
                    statement_date,
                    processed_at,
                    remitx_bank_account,
                    deposit_repo,
                    transaction_repo,
                    account_repo,
                    actor_user_id=actor_user_id,
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
    currency: str,
    fingerprint: str,
    statement_date: datetime,
    processed_at: datetime,
    remitx_bank_account: Account,
    deposit_repo: DepositRepository,
    transaction_repo: TransactionRepository,
    account_repo: AccountRepository,
    *,
    actor_user_id: uuid.UUID | None = None,
) -> Deposit:
    account = _find_account(reference, currency, account_repo)
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
                currency=currency,
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

    transaction = transaction_repo.add(
        Transaction(
            type=TYPE_DEPOSIT,
            credit_account_id=remitx_bank_account.account_id,
            debit_account_id=account.account_id,
            amount=amount,
            currency=currency,
            status=STATUS_CONFIRMED,
            created_at=statement_date,
            processed_at=processed_at,
            confirmed_at=processed_at,
        )
    )
    account_repo.decrease_balance(remitx_bank_account.account_id, amount)
    account_repo.increase_balance(account.account_id, amount)
    deposit = deposit_repo.add(
        Deposit(
            tx_id=transaction.tx_id,
            user_id=account.user_id,
            user_account_reference=reference,
            confirmed_by=CONFIRMED_BY_SYSTEM,
            statement_fingerprint=fingerprint,
        )
    )
    if actor_user_id is not None:
        from remitx_api.services.audit_service import record_audit

        record_audit(
            actor_user_id=actor_user_id,
            action=AuditAction.CASHIN_CONFIRMED,
            subject_type=AuditSubject.DEPOSIT,
            subject_id=deposit.deposit_id,
            after={
                "status": "confirmed",
                "auto_matched": True,
                "user_id": str(account.user_id),
                "account_reference": reference,
            },
        )
    return deposit


def _parse_statement_date(value, processed_at: datetime) -> datetime:
    """The date the bank statement recorded for this line — becomes the
    transaction's `created_at` (rather than "when the row was inserted"),
    so a deposit is ordered, and reported on, by when the money actually
    moved.

    Falls back to `processed_at` when the row didn't carry a date.
    """
    parsed = _try_parse_statement_datetime(value, processed_at)
    return parsed if parsed is not None else processed_at


def _find_account(
    reference: str | None, currency: str, account_repo: AccountRepository
) -> Account | None:
    """The account a bank-statement line credits: the one its reference
    names, if that account is in the line's currency. A reference to the
    customer's account in another currency, or to their token account, never
    is, and the line waits for an admin like any unmatched line.
    """
    if not reference:
        return None
    account = account_repo.get_user_account_by_reference(reference)
    if account is None:
        return None
    if account.account_currency != currency:
        logger.info(
            "Reference %s names a %s account but the line is in %s",
            reference,
            account.account_currency,
            currency,
        )
        return None
    return account


def _bank_account(currency: str, account_repo: AccountRepository) -> Account:
    """RemitX's bank account in `currency`: where a deposit in that currency
    comes in, and so the source leg of its transaction."""
    bank_account = account_repo.get_platform_account(TYPE_PLATFORM_FIAT, currency)
    if bank_account is None:
        logger.error("No RemitX platform bank account seeded for currency %s", currency)
        raise PlatformBankAccountMissingError(currency)
    return bank_account


def _read_bank_statement(bank_statement: str | list[dict]) -> list[dict]:
    """Normalize a CSV path or an already-parsed list of rows into rows."""
    if isinstance(bank_statement, list):
        return bank_statement
    try:
        with open(bank_statement, newline="") as csv_file:
            return list(csv.DictReader(csv_file))
    except (OSError, csv.Error):
        logger.error("Failed to read bank statement file %r", bank_statement)
        raise


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
    account by its reference (``sipho1-zar``, ``sipho1-usd``, …), which must
    be in the deposit's currency: a ZAR deposit lands on a ZAR account, never
    on a USD or token one.

    Raises if the deposit isn't pending (already confirmed, or doesn't exist)
    — the guarded transition on its transaction is what stops two admins from
    both confirming the same deposit.
    """
    deposit_repo = DepositRepository()
    transaction_repo = TransactionRepository()
    account_repo = AccountRepository()

    deposit = deposit_repo.get_by_id(deposit_id)
    if deposit is None:
        logger.warning("Approve failed: deposit %s does not exist", deposit_id)
        raise DepositNotPendingError()
    transaction = transaction_repo.get_by_id(deposit.tx_id)

    reference = account_reference.strip().lower()
    matched = account_repo.get_user_account_by_reference(reference)
    if matched is None:
        logger.warning(
            "Approve failed: reference %s on deposit %s matches no account",
            reference,
            deposit_id,
        )
        raise UnknownDepositReferenceError()
    if matched.account_currency != transaction.currency:
        logger.warning(
            "Approve failed: deposit %s is %s but reference %s is a %s account",
            deposit_id,
            transaction.currency,
            reference,
            matched.account_currency,
        )
        raise DepositCurrencyMismatchError(
            transaction.currency, matched.account_currency
        )

    confirmed_at = datetime.now(UTC)
    if not transaction_repo.confirm_pending_deposit_transaction(
        deposit.tx_id, matched.account_id, confirmed_at
    ):
        logger.warning(
            "Approve failed: deposit %s was no longer pending by confirm time",
            deposit_id,
        )
        raise DepositNotPendingError()

    account_repo.decrease_balance(transaction.credit_account_id, transaction.amount)
    account_repo.increase_balance(matched.account_id, transaction.amount)
    deposit_repo.link_deposit_to_user(deposit_id, matched.user_id, str(admin_id))
    from remitx_api.models.orm.audit_log import AuditAction, AuditSubject
    from remitx_api.services.audit_service import record_audit

    record_audit(
        actor_user_id=admin_id,
        action=AuditAction.CASHIN_CONFIRMED,
        subject_type=AuditSubject.DEPOSIT,
        subject_id=deposit_id,
        before={"status": "pending"},
        after={
            "status": "confirmed",
            "auto_matched": False,
            "user_id": str(matched.user_id),
            "account_reference": reference,
        },
    )

    db.session.commit()
    return deposit_repo.get_by_id(deposit_id)
