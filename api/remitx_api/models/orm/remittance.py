"""
A record is added to the table when a confirmed send occurs.

Deliberately lean: `Quote` already freezes every priced field (fx rates,
fees, token amounts, currencies) and who confirmed it (`Quote.sender_user_id`
— `confirm_remittance` only ever confirms a quote against its own sender, so
a separate `confirmed_by` here would just duplicate that column).

A `Remittance` record marks that a `Quote` was actually confirmed and links
to the one `Transaction` whose status represents whether the whole thing
settled. `quote_id` is UNIQUE: a quote can be confirmed into a remittance at
most once.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Remittance(Base):
    __tablename__ = "remittances"

    remittance_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    quote_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("quotes.quote_id"), nullable=False, unique=True
    )
    # The sender -> beneficiary token transfer (Transaction.type == TYPE_REMITTANCE)
    tx_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        server_default=text("now()"),
    )
