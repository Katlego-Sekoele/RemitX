"""
ZAR cash-in header (Transaction_Flow_Context.md Phase A).

One row per bank statement line, written the instant it's seen — matched or
not. `tx_id` always points at the one `transactions` row this deposit is:

- Matched at import -> that row is `confirmed` immediately, `user_id` set,
  `confirmed_by='system'`.
- Unmatched -> that row is inserted `pending` with `debit_account_id` NULL
  (see models/orm/transaction.py), `user_id` NULL, `user_account_reference`
  holding whatever the bank statement gave. An admin resolves it later
  (see `DepositRepository.link_deposit_to_user` +
  `TransactionRepository.confirm_pending_deposit_transaction`)
  by confirming that *same* row, never a new one.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Text, Uuid
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


def utcnow() -> datetime:
    return datetime.now(UTC)


class Deposit(Base):
    __tablename__ = "deposits"

    deposit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tx_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=False
    )
    # Nullable until an admin resolves an unmatched line.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    user_account_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method: Mapped[str] = mapped_column(
        Text, nullable=False, default=PAYMENT_METHOD_BANK_TRANSFER
    )
    # Admin id, or 'system' if matched automatically at import. NULL until resolved.
    confirmed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
