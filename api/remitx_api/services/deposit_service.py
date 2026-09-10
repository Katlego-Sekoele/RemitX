import csv
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from remitx_api.extensions import db
from remitx_api.models.orm.account import CURRENCY_ZAR, Account
from remitx_api.models.orm.deposit import CONFIRMED_BY_SYSTEM, Deposit
from remitx_api.models.orm.transaction import (
    STATUS_CONFIRMED,
    STATUS_PENDING,
    TYPE_DEPOSIT,
    Transaction,
)
from remitx_api.repositories.account_repository import AccountRepository
from remitx_api.repositories.deposit_repository import DepositRepository
from remitx_api.repositories.transaction_repository import TransactionRepository
from remitx_api.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Hand-seeded platform account every deposit's source leg debits from.
REMITX_SA_BANK_ACCOUNT_LABEL = "RemitX SA Bank Account"


def process_deposits(bank_statement: str | list[dict]) -> list[Deposit]:
    """The daily reconciliation job — simulated for this project through the
    admin pushing a button on the admin portal page that executes the job.
    """
    deposit_repo = DepositRepository()
    transaction_repo = TransactionRepository()
    account_repo = AccountRepository()

    touched = [
        _create_deposit(row, deposit_repo, transaction_repo, account_repo)
        for row in _read_bank_statement(bank_statement)
    ]

    # Anything that didn't match a user lands as a pending transaction and
    # stays that way — no automatic retry. get_pending_deposits() is what the
    # admin portal calls to list them for manual review, and
    # approve_pending_deposit() is what it calls once an admin has picked
    # the right user for one.
    db.session.commit()
    return touched


def _create_deposit(
    row: dict,
    deposit_repo: DepositRepository,
    transaction_repo: TransactionRepository,
    account_repo: AccountRepository,
) -> Deposit:
    """Match one bank statement line to an account and write its deposit + transaction.

    - Matched: transaction inserted `confirmed`, crediting the account
      immediately.
    - Unmatched: transaction inserted `pending` with no destination account
      yet, keeping the statement's own reference so an admin can resolve it
      manually — see `get_pending_deposits` / `approve_pending_deposit`.

    `row`'s "date" becomes the transaction's `created_at` — see `_parse_statement_date`.
    """
    reference = row.get("reference")
    amount = Decimal(str(row.get("amount")))
    processed_at = datetime.now(UTC)
    statement_date = _parse_statement_date(row.get("date"), processed_at)
    bank_account = account_repo.get_platform_account(REMITX_SA_BANK_ACCOUNT_LABEL)

    account = _find_account(reference, account_repo)
    if account is None:
        logger.info(
            "No account found for reference %s (amount=%s): recording as pending",
            reference,
            amount,
        )
        transaction = transaction_repo.add(
            Transaction(
                type=TYPE_DEPOSIT,
                credit_account_id=bank_account.account_id,
                debit_account_id=None,
                amount=amount,
                currency=CURRENCY_ZAR,
                status=STATUS_PENDING,
                created_at=statement_date,
            )
        )
        return deposit_repo.add(
            Deposit(tx_id=transaction.tx_id, user_reference=reference)
        )

    transaction = transaction_repo.add(
        Transaction(
            type=TYPE_DEPOSIT,
            credit_account_id=bank_account.account_id,
            debit_account_id=account.account_id,
            amount=amount,
            currency=CURRENCY_ZAR,
            status=STATUS_CONFIRMED,
            created_at=statement_date,
            confirmed_at=processed_at,
        )
    )
    account_repo.increase_balance(account.account_id, amount)
    return deposit_repo.add(
        Deposit(
            tx_id=transaction.tx_id,
            user_id=account.user_id,
            user_reference=reference,
            confirmed_by=CONFIRMED_BY_SYSTEM,
        )
    )


def _parse_statement_date(value, processed_at: datetime) -> datetime:
    """The date the bank statement recorded for this line — becomes the
    transaction's `created_at` (rather than "when the row was inserted"),
    so a deposit is ordered, and reported on, by when the money actually
    moved.

    Falls back to `processed_at` when the row didn't carry a date, or it
    can't be parsed — one bad or missing value shouldn't fail the import.
    """
    if not value:
        return processed_at
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            logger.warning("Unparseable statement date %r; using processed_at", value)
            return processed_at
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _find_account(
    reference: str | None, account_repo: AccountRepository
) -> Account | None:
    """Look up the ZAR account a bank-statement reference belongs to.

    Scoped to ZAR only — this is the statement's own currency, and the only
    currency a deposit can ever match against. Never widen this to "any of
    the user's accounts": a beneficiary's uctusd reference (e.g.
    "sian1-tok") must never resolve as a deposit target.
    """
    if not reference:
        return None
    return account_repo.get_by_reference(reference, CURRENCY_ZAR)


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
    """Get all deposits from the database for a user."""
    return DepositRepository().list_for_user(user_id)


def get_pending_deposits() -> list[Deposit]:
    """Deposits still unmatched to a user, for the admin portal to list and
    let an admin manually resolve — see `approve_pending_deposit`."""
    return DepositRepository().list_pending()


def approve_pending_deposit(
    deposit_id: uuid.UUID, user_id: uuid.UUID, admin_id: uuid.UUID
) -> Deposit:
    """An admin manually links a pending deposit to a user and confirms it.

    The admin-triggered counterpart to automatic matching in
    `_create_deposit` — used when a bank statement line's reference didn't
    match anyone at import time (e.g. a typo, or an unregistered sender) and
    an admin has since worked out, from the portal's pending list, which
    user it actually belongs to.

    Raises ValueError if the deposit isn't pending (already confirmed, or
    doesn't exist) — the guarded transition on its transaction is what
    stops two admins from both confirming the same deposit.
    """
    deposit_repo = DepositRepository()
    transaction_repo = TransactionRepository()
    account_repo = AccountRepository()
    user_repo = UserRepository()

    deposit = deposit_repo.get_by_id(deposit_id)
    if deposit is None:
        raise ValueError(f"Deposit {deposit_id} does not exist")

    transaction = transaction_repo.get_by_id(deposit.tx_id)
    user = user_repo.get_by_id(user_id)
    if user is None:
        raise ValueError(f"User {user_id} does not exist")

    user_account = account_repo.get_user_account(user.id, CURRENCY_ZAR)
    if user_account is None:
        # Should never happen post-eager-creation — defensive, not a normal path.
        raise ValueError(f"User {user_id} has no ZAR account")

    confirmed_at = datetime.now(UTC)
    if not transaction_repo.confirm_with_destination(
        deposit.tx_id, user_account.account_id, confirmed_at
    ):
        raise ValueError(f"Deposit {deposit_id} is not pending or does not exist")

    account_repo.increase_balance(user_account.account_id, transaction.amount)
    deposit_repo.link_to_user(deposit_id, user_id, str(admin_id))

    db.session.commit()
    return deposit_repo.get_by_id(deposit_id)
