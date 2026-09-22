"""
ORM Model for a fetched FX rate from the external API.

Rows are never updated in place — a "refresh" is a new row. `valid_until`
is how long *this fetched price* may be quoted from (services/exchange_rate_service.py
`get_active_rate`)
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The base currency of the exchange rate. What we're are converting from.
    base_currency: Mapped[str] = mapped_column(Text, nullable=False)
    # The quote currency of the exchange rate. What we're converting to.
    quote_currency: Mapped[str] = mapped_column(Text, nullable=False)
    # The actual exchange rate value, e.g. 18.5 for USD -> ZAR.
    rate: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # Time at which this exchange rate was fetched from the external API.
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=func.now(),
    )
    valid_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
