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

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, Uuid
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

TRANSACTION_TYPES = (
    TYPE_DEPOSIT,
    TYPE_TREASURY_FUNDING,
    TYPE_REMITTANCE,
    TYPE_FEE,
    TYPE_WITHDRAWAL,
    TYPE_TOKEN_BURN,
    TYPE_BENEFICIARY_PAYOUT,
)

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_CONFIRMED = "confirmed"
STATUS_FAILED = "failed"

STATUSES = (STATUS_PENDING, STATUS_PROCESSING, STATUS_CONFIRMED, STATUS_FAILED)


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        # Type must be in TRANSACTION_TYPES
        CheckConstraint(
            "type IN ('deposit','treasury_funding','remittance','fee','withdrawal',"
            "'token_burn','beneficiary_payout')",
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
    ) # groups legs of a remittance together
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Set only on a `burn` leg once its Payment(treasury -> issuer) validates
    # on the XRPL testnet
    xrpl_tx_hash: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
