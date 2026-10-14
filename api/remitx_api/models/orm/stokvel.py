"""
A stokvel: a group that contributes a fixed UCTUSD amount each round and pays
the pool out to one member per round (see CONTEXT.md).

`id`, packed left-aligned into `bytes32`, is the stokvel's on-chain id (the
MVP choice; see "Contract IDs" in docs/stokvel_integration.md).
The contract holds only the UCTUSD side; name, Organiser and Stokvel currency
live here. `contribution_amount` is that fixed UCTUSD amount for the
stokvel's life (the value sent to `createStokvel`; MVP: a new amount means a
new stokvel). Members are debited fiat = amount × live rate at contribution.
`deactivated_at` is when the stokvel was decommissioned, and null while it
is in service.
`account_id` is its `STOKVEL` ledger account (D9), which holds a released
pool until the payout sends it on. Nullable because the account is created
with `AccountRepository.create_stokvel_account`, after the stokvel row.
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
    # Fixed UCTUSD amount (createStokvel); fiat debit = this × live rate
    contribution_amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
    # Null while the stokvel is in service
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
