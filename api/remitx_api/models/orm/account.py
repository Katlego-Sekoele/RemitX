"""
Every party that can hold a balance — a real user, RemitX itself, or an
external counterparty — is one row here. Platform accounts (RemitX's bank
accounts, XRPL treasury wallet, fee revenue, ...) are hand-seeded by
`scripts/seed_platform_accounts.py` with `user_id` set to the administering
admin's own id — an admin is a `User` row too. Only a genuinely `EXTERNAL`
row (Kraken - a crypto exchange) has `user_id` NULL.

One row per (user_id, account_currency) for a `USER` row — a user with both
ZAR and token activity has two rows as they then have a Zar account and a
token account, not one multi-currency row. Every user gets a ZAR account by
default, alongside their uctusd account — both created eagerly, together,
at signup, from the user's own `User.base_reference` — see `create_user_accounts`
on `AccountRepository`.
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
from remitx_api.config import Config
from remitx_api.extensions import Base

TYPE_USER = "USER"
TYPE_PLATFORM_FIAT = "REMITX_FIAT"
TYPE_XRPL_WALLET = "REMITX_XRPL_WALLET"
TYPE_PLATFORM_REVENUE = "REMITX_REVENUE"
TYPE_EXTERNAL = "EXTERNAL"

ACCOUNT_TYPES = (
    TYPE_USER,
    TYPE_PLATFORM_FIAT,
    TYPE_XRPL_WALLET,
    TYPE_PLATFORM_REVENUE,
    TYPE_EXTERNAL,
)

CURRENCY_ZAR = "ZAR"
CURRENCY_TOKEN = Config().UCTUSD_TOKEN_NAME
CURRENCY_USD = "USD"
CURRENCY_ZWL = "ZWL"
CURRENCY_NAD = "NAD"


class PayoutCurrency(StrEnum):
    """What a beneficiary may be paid out in. An enum so the OpenAPI spec,
    and therefore the frontend client, carries the option list."""

    USD = CURRENCY_USD
    ZWL = CURRENCY_ZWL
    NAD = CURRENCY_NAD


PAYOUT_CURRENCIES = tuple(currency.value for currency in PayoutCurrency)

# Reference suffix per currency, e.g. "sian1-zar", "sian1-tok".
CURRENCY_REFERENCE_SUFFIX = {
    CURRENCY_ZAR: "zar",
    CURRENCY_USD: "usd",
    CURRENCY_ZWL: "zwl",
    CURRENCY_NAD: "nad",
    CURRENCY_TOKEN: "tok",
}


def create_account_reference(base_reference: str, currency: str) -> str:
    """Append a currency suffix to a user's base reference, e.g.
    ("sian1", "ZAR") -> "sian1-zar". `base_reference` is `User.base_reference`
    — computed once at signup and shared by every one of that user's accounts.
    Raises KeyError for a currency with no reference suffix.
    """
    return f"{base_reference}-{CURRENCY_REFERENCE_SUFFIX[currency]}"


class Account(Base):
    """ORM model for the `accounts` table. One row per (user_id, account_currency)"""

    __tablename__ = "accounts"  # name of the table in the database
    __table_args__ = (
        # Constraints to check type is valid
        CheckConstraint(
            "type IN ('USER','REMITX_FIAT','REMITX_XRPL_WALLET',"
            "'REMITX_REVENUE','EXTERNAL')",
            name="accounts_type_valid",
        ),
        # Constraints to check currency is valid
        CheckConstraint(
            "(type <> 'EXTERNAL' AND user_id IS NOT NULL) "
            "OR (type = 'EXTERNAL' AND user_id IS NULL)",
            name="accounts_owner_matches_type",
        ),
        # Constraints to check reference is valid
        CheckConstraint(
            "(type = 'USER' AND reference IS NOT NULL) "
            "OR (type <> 'USER' AND reference IS NULL)",
            name="accounts_reference_matches_type",
        ),
        # Constraints to check balance is non-negative for USER accounts
        CheckConstraint(
            "type <> 'USER' OR account_balance >= 0",
            name="accounts_user_balance_nonneg",
        ),
        # Index to ensure uniqueness of (user_id, account_currency) for USER accounts
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
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    # Permanent EFT reference, e.g. "sian1-zar" — USER rows only. NULL for
    # platform/external rows ( which areidentified by `label` instead).
    # Bank-statement reconciliation matches on this — see
    # AccountRepository.get_user_account_by_reference.
    reference: Mapped[str | None] = mapped_column(
        Text, nullable=True, unique=True, index=True
    )
    # Descriptive label, e.g. "Kraken" or "RemitX SA Bank Account".
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # ZAR, USD, ZWL, NAD, uctusd
    account_currency: Mapped[str] = mapped_column(Text, nullable=False)
    account_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
