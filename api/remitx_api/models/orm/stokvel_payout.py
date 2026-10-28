"""
Record of what happened when a round's pool was paid out.

- `release_status`: `pending → processing → released | failed`
  the contract releases the pool to the Treasury Wallet, and the ledger books
  the `stokvel_pool_release` leg `STOKVEL` → Treasury Wallet, so the stokvel's
  balance keeps equalling its unreleased pools. A pending row has
  sent nothing, so it has no release hash or block; a released row has its
  hash, block, ledger leg (`release_tx_id`) and `released_at`.
- `remittance_status`: the ledger's `pending → processing → confirmed | failed`
  the pool's status of remittance to the member's locked beneficiary.
  Stored here, not read through `remittance_id`.

A payout is paid once per round (UNIQUE `cycle_id`, `round`), to a cycle member
(composite FK) whom the round schedules (trigger
`stokvel_payout_member_is_scheduled`).
`round` is 0-based like the contract's `uint8 round`.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base
from remitx_api.models.orm.transaction import TransactionStatus


class StokvelPayoutReleaseStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    RELEASED = "released"
    FAILED = "failed"


class StokvelPayout(Base):
    __tablename__ = "stokvel_payouts"
    __table_args__ = (
        CheckConstraint(
            "release_status IN ('pending','processing','released','failed')",
            name="stokvel_payouts_release_status_valid",
        ),
        # Pinned on purpose, not built from `TransactionStatus`: a status added
        # there needs a migration here before a payout may use it.
        CheckConstraint(
            "remittance_status IN ('pending','processing','confirmed','failed')",
            name="stokvel_payouts_remittance_status_valid",
        ),
        CheckConstraint(
            "release_block_number IS NULL OR release_block_number >= 0",
            name="stokvel_payouts_release_block_number_nonneg",
        ),
        # Nothing is sent before the release task claims the row
        CheckConstraint(
            "release_status <> 'pending'"
            " OR (release_tx_hash IS NULL AND release_block_number IS NULL)",
            name="stokvel_payouts_pending_not_sent",
        ),
        # A block is only known for a sent transaction
        CheckConstraint(
            "release_block_number IS NULL OR release_tx_hash IS NOT NULL",
            name="stokvel_payouts_release_block_has_hash",
        ),
        # Released means mined and booked: hash, block and ledger leg are known
        CheckConstraint(
            "release_status <> 'released' OR (release_tx_hash IS NOT NULL"
            " AND release_block_number IS NOT NULL AND release_tx_id IS NOT NULL)",
            name="stokvel_payouts_released_on_chain",
        ),
        CheckConstraint(
            "(release_status = 'released') = (released_at IS NOT NULL)",
            name="stokvel_payouts_released_at_matches_status",
        ),
        # The remittance is paid from the released pool, so it waits for it
        CheckConstraint(
            "release_status = 'released' OR (remittance_status = 'pending'"
            " AND quote_id IS NULL AND remittance_id IS NULL)",
            name="stokvel_payouts_remittance_after_release",
        ),
        CheckConstraint(
            "remittance_id IS NULL OR quote_id IS NOT NULL",
            name="stokvel_payouts_remittance_has_quote",
        ),
        CheckConstraint(
            "burn_tx_hash IS NULL OR remittance_id IS NOT NULL",
            name="stokvel_payouts_burn_has_remittance",
        ),
        # Confirmed means burnt and credited: brief §7.2 keeps the burn hash
        # and remittance reference together
        CheckConstraint(
            "remittance_status <> 'confirmed' OR burn_tx_hash IS NOT NULL",
            name="stokvel_payouts_confirmed_has_burn",
        ),
        UniqueConstraint("cycle_id", "round", name="uq_stokvel_payouts_cycle_id_round"),
        ForeignKeyConstraint(
            ["cycle_id", "round"],
            ["stokvel_rounds.cycle_id", "stokvel_rounds.round"],
        ),
        ForeignKeyConstraint(
            ["cycle_id", "member_id"],
            ["stokvel_cycle_members.cycle_id", "stokvel_cycle_members.member_id"],
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # The cycle this payout belongs to
    cycle_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # The round being paid out, counting from 0
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    # The member who receives this round's pool
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # Status for whether the contract has released the round's pool to the
    # Treasury Wallet. Starts `pending`, becomes `processing` while the worker
    # sends `finalise`, and `released` once the release is recorded.
    release_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=StokvelPayoutReleaseStatus.PENDING.value,
        server_default=StokvelPayoutReleaseStatus.PENDING.value,
    )
    # The on-chain transaction that released the pool. Not unique: one
    # transaction can release several overdue rounds at once
    release_tx_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The block the release transaction was mined in
    release_block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # The ledger entry moving the pool from the stokvel to the Treasury Wallet
    release_tx_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=True, unique=True
    )
    # Status of whether the released pool has been paid on to the member's
    # beneficiary. Stays `pending` payout is `released`, becomes
    # `processing` when the worker creates the remittance, then `confirmed`
    # once the token burn settles, or `failed` if the burn fails or the
    # beneficiary can no longer be paid
    remittance_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=TransactionStatus.PENDING.value,
        server_default=TransactionStatus.PENDING.value,
    )
    # The FX quote used to price the payout
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("quotes.quote_id"), nullable=True, unique=True
    )
    # The remittance that pays the member
    remittance_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("remittances.remittance_id"), nullable=True, unique=True
    )
    # The on-chain transaction that burnt the tokens
    burn_tx_hash: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    # When we recorded the release (not the block's time). Set only once
    # `release_status` is `released`
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the worker last queued a payout for remittance, so it waits a few
    # minutes before queueing it again
    settle_queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
