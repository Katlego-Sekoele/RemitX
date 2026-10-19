"""Contract events the event sync could not apply yet (R2-13, #235).

`stokvel.sync_events` moves its cursor past every event it reads. An event it
cannot apply now is held here instead, so it is neither lost nor allowed to
stop the sync:

- `waiting`: nothing has gone wrong; something it needs does not exist yet
  (a `RoundFinalised` before the release task, R3-04, can record it; a
  `CycleClosed` before every round's payout is recorded)
- `failed`: applying it raised, or it did not decode, or it disagrees with
  the database (a contribution the database failed, a different transaction
  hash): `error` says why, for a person

Every sync run retries the unresolved rows first, in chain order, and sets
`resolved_at` once one applies. One row per log (`tx_hash`, `log_index`) per
contract. Worker-only: row-level security admits no customer session.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base

HELD_WAITING = "waiting"
HELD_FAILED = "failed"


class StokvelHeldEvent(Base):
    __tablename__ = "stokvel_held_events"
    __table_args__ = (
        CheckConstraint(
            f"reason IN ('{HELD_WAITING}', '{HELD_FAILED}')",
            name="stokvel_held_events_reason_valid",
        ),
        CheckConstraint(
            "args IS NOT NULL OR raw_log IS NOT NULL",
            name="stokvel_held_events_has_event",
        ),
        UniqueConstraint(
            "contract_address",
            "tx_hash",
            "log_index",
            name="uq_stokvel_held_events_log",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The contract address, lowercase, as `StokvelSyncState.id`
    contract_address: Mapped[str] = mapped_column(Text, nullable=False)
    tx_hash: Mapped[str] = mapped_column(Text, nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # The event's name; null for a log that did not decode
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The decoded arguments, bytes as 0x hex; null for a log that did not decode
    args: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # The raw log, kept only when it did not decode, to try again later
    raw_log: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    # Set once it applies; unresolved rows are retried on every run
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
