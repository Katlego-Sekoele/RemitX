"""
One cycle of a stokvel: a full rotation in which every member in it is paid
once (see CONTEXT.md).

A cycle is `forming` while the Organiser sets the payout order and members
choose their beneficiaries, `active` once started (membership, order and
beneficiaries locked; registered on-chain with `startCycle`), and `closed`
after its last round is released. A stokvel has at most one cycle that is not
closed, as the contract allows only one open cycle.

`total_rounds` is the number of members in the cycle (one round each), set when
it starts. `current_round` is 0-based like the contract's `uint8 round`: round
i pays the member at `payout_position` i.

Starting a cycle (R2-10) makes it `active` at once; the worker then registers
it on-chain (`createStokvel` for a new stokvel, then `startCycle`).
`start_tx_hash` is that `startCycle`, stored before it is sent;
`start_block_number` and `registered_at` are set once it is mined, and
contributions are refused until then (the contract has no open cycle before).
`registered_at` may be set without the hash or block, when the worker finds
the cycle already open on-chain.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class StokvelCycleStatus(StrEnum):
    FORMING = "forming"
    ACTIVE = "active"
    CLOSED = "closed"


class StokvelCycle(Base):
    __tablename__ = "stokvel_cycles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('forming','active','closed')",
            name="stokvel_cycles_status_valid",
        ),
        CheckConstraint("cycle_number >= 1", name="stokvel_cycles_number_positive"),
        CheckConstraint(
            "(status = 'forming') = (started_at IS NULL)",
            name="stokvel_cycles_started_at_matches_status",
        ),
        CheckConstraint(
            "(status = 'closed') = (closed_at IS NOT NULL)",
            name="stokvel_cycles_closed_at_matches_status",
        ),
        # A started cycle has a fixed number of rounds, one per member
        CheckConstraint(
            "status = 'forming' OR total_rounds IS NOT NULL",
            name="stokvel_cycles_started_has_total_rounds",
        ),
        CheckConstraint(
            "total_rounds IS NULL OR total_rounds >= 2",
            name="stokvel_cycles_total_rounds_min",
        ),
        CheckConstraint(
            "current_round IS NULL "
            "OR (current_round >= 0 AND current_round < total_rounds)",
            name="stokvel_cycles_current_round_in_range",
        ),
        # Registration on-chain begins only once the cycle has started
        CheckConstraint(
            "status <> 'forming' OR (start_tx_hash IS NULL AND registered_at IS NULL)",
            name="stokvel_cycles_forming_not_registered",
        ),
        CheckConstraint(
            "start_block_number IS NULL OR registered_at IS NOT NULL",
            name="stokvel_cycles_start_block_is_registered",
        ),
        CheckConstraint(
            "start_block_number IS NULL OR start_block_number >= 0",
            name="stokvel_cycles_start_block_nonneg",
        ),
        UniqueConstraint(
            "stokvel_id", "cycle_number", name="uq_stokvel_cycles_stokvel_id_number"
        ),
        UniqueConstraint("start_tx_hash", name="stokvel_cycles_start_tx_hash_key"),
        # One open cycle per stokvel, as the contract's startCycle requires
        Index(
            "uq_stokvel_cycles_open",
            "stokvel_id",
            unique=True,
            postgresql_where=text("status <> 'closed'"),
            sqlite_where=text("status <> 'closed'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    stokvel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stokvels.id"), nullable=False, index=True
    )
    # The number of the cycle in the stokvel. Starts at 1.
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=StokvelCycleStatus.FORMING.value,
        server_default=StokvelCycleStatus.FORMING.value,
    )
    # The total number of rounds in the cycle. Set when the cycle starts.
    total_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Starts at 0 when the cycle starts
    current_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Cycle start date
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Cycle end date
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The `startCycle` transaction, stored before it is sent (R2-10)
    start_tx_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # When the worker recorded the cycle as open on-chain; contributions wait
    # for it
    registered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
