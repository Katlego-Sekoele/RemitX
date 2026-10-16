"""
A member's contribution to one round of a stokvel cycle (see CONTEXT.md).

The member's fiat account is debited `amount_fiat` (the stokvel's fixed
`contribution_amount` of UCTUSD at the live rate, D13), and the worker sends
`amount_token` UCTUSD from the Treasury Wallet to the contract with
`contribute`. Who has paid a round is derived from these rows, not stored.

Status follows the ledger (`pending -> processing -> confirmed | failed`):

- `pending`: recorded with its ledger legs; nothing sent on-chain, so no hash
- `processing`: claimed by the worker. The hash is stored before the send (as
  for the burn, #278), so a processing row may already have one
- `confirmed`: `contribute` was mined: hash, block and `confirmed_at` are set
- `failed`: nothing was recorded on-chain; the member may pay the round again

A member pays a round once: the partial unique index
`uq_stokvel_contributions_once` allows one row per (cycle, round, member)
that has not failed. A failed attempt stays as history, and a retry is a new
row. The contract's `AlreadyPaid` is the second line of defence. Instalments
cannot happen: `contribute` always pulls the full fixed amount.

The composite foreign keys keep a contribution inside its cycle: the round
must be one of the cycle's rounds, and the member one of the cycle's members.

`tx_id` points at a ledger leg of the contribution. Which leg, and how the
legs are grouped, is decided by the contribution API (R2-11, #233).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base


class StokvelContributionStatus(StrEnum):
    """The ledger's states (doc section 3); a contribution moves through them
    like its legs do."""

    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    FAILED = "failed"


STATUS_PENDING = StokvelContributionStatus.PENDING.value
STATUS_CONFIRMED = StokvelContributionStatus.CONFIRMED.value
STATUS_FAILED = StokvelContributionStatus.FAILED.value


class StokvelContribution(Base):
    __tablename__ = "stokvel_contributions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','confirmed','failed')",
            name="stokvel_contributions_status_valid",
        ),
        CheckConstraint("round >= 0", name="stokvel_contributions_round_nonneg"),
        CheckConstraint(
            "amount_token > 0", name="stokvel_contributions_amount_token_positive"
        ),
        CheckConstraint(
            "amount_fiat > 0", name="stokvel_contributions_amount_fiat_positive"
        ),
        CheckConstraint(
            "block_number IS NULL OR block_number >= 0",
            name="stokvel_contributions_block_number_nonneg",
        ),
        # Nothing is sent before the worker claims the row
        CheckConstraint(
            f"status <> '{STATUS_PENDING}'"
            " OR (evm_tx_hash IS NULL AND block_number IS NULL)",
            name="stokvel_contributions_pending_not_sent",
        ),
        # A block is only known for a sent transaction
        CheckConstraint(
            "block_number IS NULL OR evm_tx_hash IS NOT NULL",
            name="stokvel_contributions_block_has_hash",
        ),
        # Confirmed means mined: its hash and block are known
        CheckConstraint(
            f"status <> '{STATUS_CONFIRMED}'"
            " OR (evm_tx_hash IS NOT NULL AND block_number IS NOT NULL)",
            name="stokvel_contributions_confirmed_on_chain",
        ),
        CheckConstraint(
            f"(status = '{STATUS_CONFIRMED}') = (confirmed_at IS NOT NULL)",
            name="stokvel_contributions_confirmed_at_matches_status",
        ),
        # The round is one of the cycle's rounds
        ForeignKeyConstraint(
            ["cycle_id", "round"],
            ["stokvel_rounds.cycle_id", "stokvel_rounds.round"],
            name="stokvel_contributions_round_fkey",
        ),
        # The member is one of the cycle's members
        ForeignKeyConstraint(
            ["cycle_id", "member_id"],
            ["stokvel_cycle_members.cycle_id", "stokvel_cycle_members.member_id"],
            name="stokvel_contributions_cycle_member_fkey",
        ),
        # One contribution per member per round, unless it failed
        Index(
            "uq_stokvel_contributions_once",
            "cycle_id",
            "round",
            "member_id",
            unique=True,
            postgresql_where=text(f"status <> '{STATUS_FAILED}'"),
            sqlite_where=text(f"status <> '{STATUS_FAILED}'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    cycle_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # 0-based, the contract's `uint8 round`
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    # The on-chain memberId: a stokvel_members row in this cycle
    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    # UCTUSD sent to the contract: the stokvel's fixed contribution_amount
    amount_token: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # Debited from the member's account in the Stokvel currency
    amount_fiat: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=STATUS_PENDING,
        server_default=STATUS_PENDING,
    )
    # A ledger leg of this contribution (R2-11 decides which)
    tx_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.tx_id"), nullable=True, unique=True
    )
    # The `contribute` transaction, stored before it is sent
    evm_tx_hash: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )  # Set to `utcnow()` on insert, never updated.
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
