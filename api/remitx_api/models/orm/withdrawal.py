"""
A withdrawal request: fiat leaving a user's own currency account for their
external bank account.

Deliberately lean, status lives on the linked `Transaction` rows, not
duplicated here. `tx_id` is the withdrawal transaction (RemitX bank account
-> user's bank account); `fee_tx_id` is the cash-out fee transaction.
Every withdrawal has one: the fee is never below 0.01 (see
Config.MIN_CASH_OUT_FEE).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    withdrawal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tx_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=False
    )
    fee_tx_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    bank_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("bank_accounts.bank_account_id"), nullable=False
    )
    # Requested amount that leaves the user's RemitX account (fee + net).
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # What actually lands in the user's bank account (gross - fee).
    net_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    # Always 'system': withdrawals settle on request, never by an admin
    confirmed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
