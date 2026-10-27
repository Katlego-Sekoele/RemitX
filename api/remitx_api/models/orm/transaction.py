"""
Ledger entry (Transaction_Flow_Context.md §1).

Every movement of money — a deposit, a fee, a remittance leg, a withdrawal
leg, a treasury top-up — is one row here: `credit_account_id` is the source,
`debit_account_id` the destination. The only table with a `status`
lifecycle; `accounts.account_balance` only ever changes as part of a
guarded `pending -> confirmed` transition on one of these rows, in the same
commit.

`debit_account_id` is nullable: an unmatched deposit is inserted `pending`
with its destination not yet known, then confirmed in place once an admin
resolves it — see models/orm/deposit.py.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from remitx_api.clock import utcnow
from remitx_api.extensions import Base

TYPE_DEPOSIT = "deposit"
TYPE_TREASURY_FUNDING = "treasury_funding"
TYPE_REMITTANCE = "remittance"
TYPE_FEE = "fee"
TYPE_WITHDRAWAL = "withdrawal"
TYPE_TOKEN_BURN = "token_burn"
# The beneficiary's fiat payout from the platform's fiat account.
TYPE_BENEFICIARY_PAYOUT = "beneficiary_payout"
# A member's contribution into a stokvel round (Treasury -> the stokvel's
# `STOKVEL` account), and a round's pool released back out of it (`STOKVEL`
# -> Treasury), so `STOKVEL` holds what the contract holds
# (docs/stokvel_integration.md §3).
TYPE_STOKVEL_CONTRIBUTION = "stokvel_contribution"
TYPE_STOKVEL_POOL_RELEASE = "stokvel_pool_release"

TRANSACTION_TYPES = (
    TYPE_DEPOSIT,
    TYPE_TREASURY_FUNDING,
    TYPE_REMITTANCE,
    TYPE_FEE,
    TYPE_WITHDRAWAL,
    TYPE_TOKEN_BURN,
    TYPE_BENEFICIARY_PAYOUT,
    TYPE_STOKVEL_CONTRIBUTION,
    TYPE_STOKVEL_POOL_RELEASE,
)


class TransactionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    CONFIRMED = "confirmed"
    FAILED = "failed"


STATUS_PENDING = TransactionStatus.PENDING.value
STATUS_PROCESSING = TransactionStatus.PROCESSING.value
STATUS_CONFIRMED = TransactionStatus.CONFIRMED.value
STATUS_FAILED = TransactionStatus.FAILED.value

STATUSES = tuple(TransactionStatus)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # Type must be in TRANSACTION_TYPES
        CheckConstraint(
            "type IN ('deposit','treasury_funding','remittance','fee','withdrawal',"
            "'token_burn','beneficiary_payout','stokvel_contribution',"
            "'stokvel_pool_release')",
            name="transactions_type_valid",
        ),
        # Status must be in STATUSES
        CheckConstraint(
            "status IN ('pending','processing','confirmed','failed')",
            name="transactions_status_valid",
        ),
        # Amount must be positive — negative amounts are represented by swapping
        # the debit/credit accounts instead.
        CheckConstraint("amount > 0", name="transactions_amount_positive"),
        # `transactions` has no round. A payout already has one quote per
        # round, so one burn leg per quote is the second burn a retry would
        # insert. A failed burn stays on that row; another attempt is a new
        # quote (docs/stokvel_integration.md §3, §8).
        Index(
            "uq_transactions_one_token_burn_per_quote",
            "quote_id",
            unique=True,
            postgresql_where=text("type = 'token_burn'"),
            sqlite_where=text("type = 'token_burn'"),
        ),
    )

    tx_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # Destination. Nullable only while an unmatched deposit is pending.
    debit_account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), nullable=True
    )
    # Source. Always known up front.
    credit_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default=STATUS_PENDING)
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("quotes.quote_id"), nullable=True
    )  # groups legs of a remittance together
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )  # Set to `utcnow()` on insert, never updated.
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set only on a `burn` leg once its burn (treasury -> issuer) is
    # confirmed on chain
    evm_tx_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True, index=True
    )
    # Deprecated: the old name of `evm_tx_hash`, still written alongside
    # it so a worker running the previous release keeps working while the
    # rename rolls out. Read `evm_tx_hash`. A later migration copies any
    # hash written only here across and drops this column.
    xrpl_tx_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True, index=True
    )
