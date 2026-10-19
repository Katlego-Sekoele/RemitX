"""The event sync's cursor (doc section 3, ticket R2-13).

`stokvel.sync_events` reads the stokvel contract's events block by block and
records here the last block it has applied. It moves the cursor in the same
transaction as the changes those blocks caused, so a crash can neither skip
events nor apply a block's changes without recording it.

One row per contract address (`id`, lowercase), so a redeploy to a new
address starts its own cursor at `STOKVEL_SYNC_START_BLOCK`. Written by the
worker only: row-level security admits no customer session.
"""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class StokvelSyncState(Base):
    __tablename__ = "stokvel_sync_state"
    __table_args__ = (
        CheckConstraint(
            "last_processed_block >= 0",
            name="stokvel_sync_state_block_nonneg",
        ),
    )

    # The contract address, lowercase
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    # Every event up to and including this block has been applied
    last_processed_block: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
