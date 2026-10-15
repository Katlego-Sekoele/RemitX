"""
A stokvel member's place in one cycle: when they are paid and where the
payout goes.

Stored per cycle because membership, payout order and beneficiary can change
between cycles but are fixed within one, and a past cycle must still show
where its money went.

- `payout_position`: 0-based, the round that pays this member (the index in
  the contract's `startCycle` member list). The members agree the order off
  the platform (D3); this is null until the Organiser enters it.
- `payout_beneficiary_id` and `payout_currency`: the beneficiary the stokvel
  pays this member's pool to directly (#293), and the currency of theirs it is
  paid in. Set together; null until the member chooses.
- `continued`: whether the member stays for the next cycle once this one ends
  (R2-15). Null until they choose.
- `locked`: set when the cycle starts; the order and beneficiary may not
  change after that.
"""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.extensions import Base
from remitx_api.models.orm.account import PAYOUT_CURRENCIES

_CURRENCY_CHECK_VALUES = ", ".join(f"'{value}'" for value in PAYOUT_CURRENCIES)


class StokvelCycleMember(Base):
    __tablename__ = "stokvel_cycle_members"
    __table_args__ = (
        CheckConstraint(
            "payout_position IS NULL OR payout_position >= 0",
            name="stokvel_cycle_members_position_nonneg",
        ),
        CheckConstraint(
            f"payout_currency IN ({_CURRENCY_CHECK_VALUES})",
            name="stokvel_cycle_members_payout_currency_valid",
        ),
        CheckConstraint(
            "(payout_beneficiary_id IS NULL) = (payout_currency IS NULL)",
            name="stokvel_cycle_members_beneficiary_has_currency",
        ),
        # A cycle starts only once every member has a position and a beneficiary
        CheckConstraint(
            "NOT locked "
            "OR (payout_position IS NOT NULL AND payout_beneficiary_id IS NOT NULL)",
            name="stokvel_cycle_members_locked_is_complete",
        ),
        UniqueConstraint(
            "cycle_id",
            "payout_position",
            name="uq_stokvel_cycle_members_cycle_id_position",
        ),
    )
    # The cycle this member is part of
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stokvel_cycles.id"), primary_key=True
    )
    # The on-chain memberId. Points to a StokvelMember in stokvel_members.
    member_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("stokvel_members.id"), primary_key=True, index=True
    )
    # Which round pays this member in this cycle
    payout_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payout_beneficiary_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("beneficiaries.beneficiary_id"), nullable=True
    )
    payout_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    continued: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Set when the cycle starts to lock the payout order and beneficiary.
    locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
