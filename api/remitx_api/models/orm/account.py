"""
Ledger account (Transaction_Flow_Context.md §1).

Every party that can hold a balance — a real user, RemitX itself, or an
external counterparty — is one row here. A `USER` row's `account_id` is its
own id, not the same value as `user_id`. Platform accounts (RemitX's bank
account, treasury wallet, fee revenue, ...) are hand-seeded by
`scripts/seed_platform_accounts.py` with `user_id` set to the administering
admin's own id — an admin is a `User` row too. Only a genuinely `EXTERNAL`
row (Kraken, RemitXZIM — outside RemitX) has `user_id` NULL: no RemitX admin
owns a third party's account.

One row per (user_id, account_currency) for a `USER` row — a user with both
ZAR and uctusd activity has two rows, not one multi-currency row. Both are
created eagerly, together, at signup, from the user's own
`User.base_reference` — see `create_user_accounts` on `AccountRepository`.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

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

from remitx_api.extensions import Base

TYPE_USER = "USER"
TYPE_PLATFORM_FIAT = "PLATFORM_FIAT"
TYPE_XRPL_WALLET = "XRPL_WALLET"
TYPE_PLATFORM_REVENUE = "PLATFORM_REVENUE"
TYPE_EXTERNAL = "EXTERNAL"

ACCOUNT_TYPES = (
    TYPE_USER,
    TYPE_PLATFORM_FIAT,
    TYPE_XRPL_WALLET,
    TYPE_PLATFORM_REVENUE,
    TYPE_EXTERNAL,
)

CURRENCY_ZAR = "ZAR"
CURRENCY_TOKEN = "uctusd"

# Reference suffix per currency, e.g. "sian1-zar", "sian1-tok".
CURRENCY_REFERENCE_SUFFIX = {
    CURRENCY_ZAR: "zar",
    CURRENCY_TOKEN: "tok",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def account_reference(base_reference: str, currency: str) -> str:
    """Append a currency suffix to a user's base reference, e.g.
    ("sian1", "ZAR") -> "sian1-zar". `base_reference` is `User.base_reference`
    — computed once at signup, shared by every one of that user's accounts.
    Raises KeyError for a currency with no reference suffix, deliberately
    loud rather than producing something unquotable.
    """
    return f"{base_reference}-{CURRENCY_REFERENCE_SUFFIX[currency]}"


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "type IN ('USER','PLATFORM_FIAT','XRPL_WALLET',"
            "'PLATFORM_REVENUE','EXTERNAL')",
            name="accounts_type_valid",
        ),
        CheckConstraint(
            "(type <> 'EXTERNAL' AND user_id IS NOT NULL) "
            "OR (type = 'EXTERNAL' AND user_id IS NULL)",
            name="accounts_owner_matches_type",
        ),
        CheckConstraint(
            "(type = 'USER' AND reference IS NOT NULL) "
            "OR (type <> 'USER' AND reference IS NULL)",
            name="accounts_reference_matches_type",
        ),
        CheckConstraint(
            "type <> 'USER' OR account_balance >= 0",
            name="accounts_user_balance_nonneg",
        ),
        # One account per user per currency. Platform/external rows are
        # hand-seeded, so they're deliberately not covered by this index.
        Index(
            "ix_accounts_user_currency",
            "user_id",
            "account_currency",
            unique=True,
            postgresql_where=text("type = 'USER'"),
            sqlite_where=text("type = 'USER'"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    # The real customer for a USER row, the administering admin for every
    # RemitX-owned platform row. NULL only for a genuinely EXTERNAL row.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # Permanent EFT reference, e.g. "sian1-zar" — USER rows only. NULL for
    # platform/external rows, identified by `label` instead. Bank-statement
    # reconciliation matches on this, scoped to one currency at a time — see
    # AccountRepository.get_by_reference.
    reference: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True, index=True
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    account_currency: Mapped[str] = mapped_column(Text, nullable=False)
    account_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
