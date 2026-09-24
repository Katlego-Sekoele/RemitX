"""
Cash-in header (Transaction_Flow_Context.md Phase A).

One row per bank statement line, written the instant it's seen — matched or
not. `tx_id` always points at the one `transactions` row this deposit is:

- Matched at import -> the reference names the customer's account in the
  line's currency. That row is `confirmed` immediately, `user_id` set,
  `confirmed_by='system'`.
- Unmatched (including a reference to an account in another currency, or a
  token account) -> that row is inserted `pending`, still in the line's
  currency, with `debit_account_id` NULL (see models/orm/transaction.py),
  `user_id` NULL, `user_account_reference` holding whatever the bank
  statement gave. An admin resolves it later, to an account in that same
  currency (see `DepositRepository.link_deposit_to_user` +
  `TransactionRepository.confirm_pending_deposit_transaction`), by
  confirming that *same* row, never a new one.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base

PAYMENT_METHOD_CASH = "cash"
PAYMENT_METHOD_BANK_TRANSFER = "bank_transfer"
PAYMENT_METHOD_CARD = "card"

PAYMENT_METHODS = (
    PAYMENT_METHOD_CASH,
    PAYMENT_METHOD_BANK_TRANSFER,
    PAYMENT_METHOD_CARD,
)

CONFIRMED_BY_SYSTEM = "system"

# UUID text from ``str(admin_id)`` when an admin confirms a pending line.
_CONFIRMED_BY_UUID_SHAPE = (
    "length(confirmed_by) = 36 AND substr(confirmed_by, 9, 1) = '-' "
    "AND substr(confirmed_by, 14, 1) = '-' AND substr(confirmed_by, 19, 1) = '-' "
    "AND substr(confirmed_by, 24, 1) = '-'"
)


class Deposit(Base):
    __tablename__ = "deposits"
    __table_args__ = (
        # One bank-statement line, one deposit. Re-uploading the same CSV
        # (or an overlapping date range) must not credit the balance again.
        UniqueConstraint(
            "statement_fingerprint",
            name="uq_deposits_statement_fingerprint",
        ),
        CheckConstraint(
            f"confirmed_by IS NULL OR confirmed_by = '{CONFIRMED_BY_SYSTEM}' OR "
            f"({_CONFIRMED_BY_UUID_SHAPE})",
            name="deposits_confirmed_by_actor",
        ),
        # Admin ids are also enforced in Postgres by
        # validate_deposits_confirmed_by() (see Alembic migration).
    )

    deposit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    # Identity of the statement line: UTC date, stripped reference, amount at
    # 2dp. See deposit_service.statement_fingerprint.
    statement_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    tx_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=False
    )
    # Nullable until an admin resolves an unmatched line. Indexed because the
    # admin reconciliation views and a user's own deposit history both filter
    # on it.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True, index=True
    )
    user_account_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method: Mapped[str] = mapped_column(
        Text, nullable=False, default=PAYMENT_METHOD_BANK_TRANSFER
    )
    # Admin id, or 'system' if matched automatically at import. NULL until resolved.
    confirmed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
