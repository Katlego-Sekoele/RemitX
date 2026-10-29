"""
One round of a stokvel cycle: a contribution period whose pool is released to
one member.

`round` is 0-based, the contract's `uint8 round`, so it passes straight to
`startCycle`, `contribute` and `finalise`. The Organiser sets the three times
before the cycle starts:

- `start_time`: when the round opens for contributions (informational)
- `deadline`: when members are expected to have paid; informational only, a
  late contribution is still accepted (D7)
- `payout_time`: the hard gate; the round cannot be released before it (D12)

The contract requires start <= deadline <= payout within a round; the rule
that times may not go backwards from one round to the next is checked when
the cycle starts.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base


class StokvelRound(Base):
    __tablename__ = "stokvel_rounds"
    __table_args__ = (
        CheckConstraint("round >= 0", name="stokvel_rounds_round_nonneg"),
        CheckConstraint(
            "start_time <= deadline AND deadline <= payout_time",
            name="stokvel_rounds_times_ordered",
        ),
    )

    cycle_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stokvel_cycles.id"), primary_key=True
    )
    # The round number within the cycle.
    round: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Hard gate (D12): the round is never released before this time. After it,
    # the round is released once the next round is fully paid (D5; the last
    # round once it is fully paid itself). A late payment still unblocks it.
    payout_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
