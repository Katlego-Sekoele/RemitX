"""
A record is added to the table when a confirmed send occurs.

Deliberately lean: `Quote` already freezes every priced field (fx rates,
fees, token amounts, currencies). 

A `Remittance` record marks that a `Quote` was actually confirmed and links to the
one `Transaction` whose status represents whether the whole thing
settled (the sender -> beneficiary token transfer, and records who confirmed it.
`quote_id` is UNIQUE: a quote can be confirmed into a remittance at most
once.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Uuid
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
    # — its status is what "has this remittance settled?" actually reads.
    tx_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=False
    )
    confirmed_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
