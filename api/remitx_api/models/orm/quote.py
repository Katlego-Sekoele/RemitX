"""
The frozen price shown to a customer for a remittance.
Nothing consumes a quote yet until a remittance confirmation.

Three currency concepts live on this row:

- `token_name`/`token_amount` — what's actually settled: uctusd, USD-pegged.
  `fiat_to_token_exchange_rate`/`fiat_to_token_exchange_rate_id` are the rate
  (and, if applicable, the stored `ExchangeRate` row) between the token and
  `sender_currency`, expressed as token units per 1 `sender_currency` (the
  inverse of `sender_currency`'s USD quote) — required, since `token_amount`
  is computed by multiplying through it (see services/quote_service.py).
  `fiat_to_token_exchange_rate_id` is nullable: it's only unpopulated when
  `sender_currency == CURRENCY_USD`, where there's no real `ExchangeRate`
  row to reference (uctusd's own peg, 1:1, needs no lookup).
- `receiver_currency`/`receiver_amount`/`receiver_payout_fee`/
  `receiver_payout_estimate` — the beneficiary's chosen payout currency and
  their estimated cash-out in it: `receiver_amount` is `sender_amount`'s net
  (post-fee) converted directly via `fiat_exchange_rate` (not routed through
  the token leg), `receiver_payout_fee`/`receiver_payout_estimate` apply
  `CASH_OUT_FEE_RATE` on top. No real cash-out flow exists yet, so this is a
  display estimate only, never a real payout (see services/quote_service.py).
- `fiat_exchange_rate`/`fiat_exchange_rate_id` — the direct fiat rate
  between the sender's currency and the beneficiary's payout currency (e.g.
  ZAR -> ZWL, fetched as its own pair, not derived from two separate
  USD-relative rates). Never affects settlement or `token_amount`, but is
  still required — always backed by a real `ExchangeRate` row, even when
  the two currencies are the same — a quote can't be issued if this rate
  isn't obtainable (see services/quote_service.py).
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, Uuid
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
    sender_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), nullable=False
    )
    beneficiary_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), nullable=False
    )
    sender_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    sender_currency: Mapped[str] = mapped_column(Text, nullable=False)
    # In the sender's currency.
    sender_transaction_fee: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    token_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # Name of the token used for settlement, e.g. "uctusd"
    token_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Required: sender_currency units per 1 token (token is 1:1 with USD).
    # Id is nullable only when sender_currency == CURRENCY_USD (no
    # ExchangeRate row to reference).
    fiat_to_token_exchange_rate_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("exchange_rates.id"), nullable=True
    )
    fiat_to_token_exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    # Required: the direct sender_currency -> beneficiary payout currency
    # rate, always backed by a real ExchangeRate row (even when the two
    # currencies match). Doesn't feed settlement math.
    fiat_exchange_rate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("exchange_rates.id"), nullable=False
    )
    fiat_exchange_rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    exchange_rate_margin: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    # Gross estimated cash-out, in receiver_currency, before receiver_payout_fee.
    receiver_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # The beneficiary's chosen payout currency (e.g. ZWL).
    receiver_currency: Mapped[str] = mapped_column(Text, nullable=False)
    receiver_payout_fee: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    receiver_payout_estimate: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default=STATUS_ACTIVE)
