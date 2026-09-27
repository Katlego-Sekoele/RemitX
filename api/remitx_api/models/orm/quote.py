"""
The frozen price shown to a customer for a remittance.
Nothing consumes a quote yet until a remittance confirmation.

Three currency concepts live on this row:

- `token_name`/`token_amount` — what's actually settled, via the USD-pegged
  token. `fiat_to_token_exchange_rate` is token units per 1 `sender_currency`
  (inverse of its USD quote); `token_amount` is computed by multiplying
  through it. `fiat_to_token_exchange_rate_id` is nullable only for
  `sender_currency == CURRENCY_USD` (1:1 peg, no `ExchangeRate` row needed).
- `receiver_currency`/`receiver_amount`/`receiver_payout_fee`/
  `receiver_payout_estimate` — the beneficiary's payout currency and cash-out
  in it. `receiver_amount` (net sender amount converted via
  `fiat_exchange_rate`, not through the token leg) is what settlement
  actually credits to the beneficiary's fiat account, with no cash-out fee deducted.
  `receiver_payout_fee`/ `receiver_payout_estimate` apply `CASH_OUT_FEE_RATE`
  on top: the quotation's estimate of a later cash-out. They are never
  charged here; a withdrawal works out its own fee when it happens.
- `fiat_exchange_rate`/`fiat_exchange_rate_id` — the direct sender-currency
  to payout-currency rate (e.g. ZAR -> ZWL, its own fetched pair, not derived
  from two USD-relative rates). Doesn't affect settlement or `token_amount`.

`sender_amount_zar` is the send's value in rand at this quote's rates: what it
counts as against the sending limits, which are in rand whatever account the
money leaves (services/send_limits.py). Locked here like the fees, so a rate
move after the quote never changes it.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ColumnElement,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base

STATUS_ACTIVE = "ACTIVE"
STATUS_USED = "USED"
STATUS_EXPIRED = "EXPIRED"

QUOTE_STATUSES = (STATUS_ACTIVE, STATUS_USED, STATUS_EXPIRED)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE','USED','EXPIRED')",
            name="quotes_status_valid",
        ),
        CheckConstraint("sender_amount > 0", name="quotes_sender_amount_positive"),
    )

    quote_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    sender_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )  # Sender user id
    beneficiary_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )  # Beneficiary user id
    sender_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # Used with sender user id to get the sender's fiat account.
    sender_currency: Mapped[str] = mapped_column(Text, nullable=False)
    # `sender_amount` in rand at this quote's rates. Read it through
    # `value_zar`: it is NULL on a quote written before the column existed,
    # until a later migration can make it NOT NULL.
    sender_amount_zar: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 8), nullable=True
    )
    sender_transaction_fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )  # In the sender's currency.
    token_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # Name of the token used for settlement, e.g. "uctusd"
    token_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Required: sender_currency units per 1 token (token is 1:1 with USD).
    # Id is nullable only when sender_currency == CURRENCY_USD (no
    # ExchangeRate row to reference).
    fiat_to_token_exchange_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("exchange_rates.id"), nullable=True
    )
    # Same as the rate between the sender currency and USD, since the token
    # is pegged to USD.
    fiat_to_token_exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    # The direct sender_currency -> beneficiary payout currency rate and record id
    fiat_exchange_rate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("exchange_rates.id"), nullable=False
    )
    fiat_exchange_rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    exchange_rate_margin: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    # What settlement credits to the beneficiary's fiat account, in
    # receiver_currency. No cash-out fee is taken from it.
    receiver_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # The beneficiary's chosen payout currency (e.g. ZWL). Used with
    # beneficiary user id to get the beneficiary's fiat account.
    receiver_currency: Mapped[str] = mapped_column(Text, nullable=False)
    receiver_payout_fee: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    receiver_payout_estimate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=STATUS_ACTIVE, server_default=STATUS_ACTIVE
    )

    @hybrid_property
    def value_zar(self) -> Decimal:
        """What the send counts as in rand. A quote written before
        `sender_amount_zar` existed can only be a ZAR one, since that code
        sent nothing else, so its amount is already in rand."""
        if self.sender_amount_zar is None:
            return self.sender_amount
        return self.sender_amount_zar

    @value_zar.inplace.expression
    @classmethod
    def _value_zar_expression(cls) -> ColumnElement[Decimal]:
        return func.coalesce(cls.sender_amount_zar, cls.sender_amount)
