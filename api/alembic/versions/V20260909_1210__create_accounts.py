"""create accounts

Ledger accounts (Transaction_Flow_Context.md §1) — every party that can
hold a balance: a real user, RemitX itself, or an external counterparty.
Platform accounts are NOT seeded here — they need a real admin's user_id,
which doesn't exist at migration time; see scripts/seed_platform_accounts.py.

Revision ID: 7b3f9a2e1c48
Revises: a1c5e08f3d67
Create Date: 2026-09-09 12:10:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b3f9a2e1c48"
down_revision: str | None = "a1c5e08f3d67"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("account_currency", sa.Text(), nullable=False),
        sa.Column("account_balance", sa.Numeric(20, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("account_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.CheckConstraint(
            "type IN ('USER','PLATFORM_FIAT','XRPL_WALLET','PLATFORM_REVENUE','EXTERNAL')",
            name="accounts_type_valid",
        ),
        # user_id: the real customer for a USER row, the administering admin
        # for every RemitX-owned platform row. NULL only for EXTERNAL.
        sa.CheckConstraint(
            "(type <> 'EXTERNAL' AND user_id IS NOT NULL) "
            "OR (type = 'EXTERNAL' AND user_id IS NULL)",
            name="accounts_owner_matches_type",
        ),
        sa.CheckConstraint(
            "(type = 'USER' AND reference IS NOT NULL) "
            "OR (type <> 'USER' AND reference IS NULL)",
            name="accounts_reference_matches_type",
        ),
        sa.CheckConstraint(
            "type <> 'USER' OR account_balance >= 0",
            name="accounts_user_balance_nonneg",
        ),
    )
    # One account per user per currency. Platform/external rows are
    # hand-seeded, so they're deliberately not covered by this index.
    op.create_index(
        "ix_accounts_user_currency",
        "accounts",
        ["user_id", "account_currency"],
        unique=True,
        postgresql_where=sa.text("type = 'USER'"),
    )
    # Permanent EFT reference, e.g. "sian1-zar" — USER rows only. NULLs
    # (every platform/external row) are excluded from a plain unique index
    # by both Postgres and SQLite, so no partial-index syntax is needed here.
    op.create_index("ix_accounts_reference", "accounts", ["reference"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_accounts_reference", table_name="accounts")
    op.drop_index("ix_accounts_user_currency", table_name="accounts")
    op.drop_table("accounts")
