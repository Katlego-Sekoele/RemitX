"""
A stokvel: a group that contributes a fixed fiat amount each round and pays
the pool out to one member per round (see CONTEXT.md).

`id`, packed left-aligned into `bytes32`, is the stokvel's on-chain id (the
MVP choice; see "Contract IDs" in docs/stokvel_integration.md).
The contract holds only the UCTUSD side; name, Organiser and Stokvel currency
live here. `contribution_amount` is fiat and fixed for the stokvel's life, as
the contract's amount is (MVP: a new amount means a new stokvel).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base
from remitx_api.models.orm.account import PAYOUT_CURRENCIES

_CURRENCY_CHECK_VALUES = ", ".join(f"'{value}'" for value in PAYOUT_CURRENCIES)


class Stokvel(Base):
    __tablename__ = "stokvels"
    __table_args__ = (
        CheckConstraint(
            f"currency IN ({_CURRENCY_CHECK_VALUES})",
            name="stokvels_currency_valid",
        ),
        CheckConstraint(
            "contribution_amount > 0",
            name="stokvels_contribution_amount_positive",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    organiser_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Stokvel currency: every contribution is paid from an account in it
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    contribution_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
