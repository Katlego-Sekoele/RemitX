"""create transactions

Ledger entries (Transaction_Flow_Context.md §1) — every movement of money.
`debit_account_id` (destination) is nullable: an unmatched deposit is
inserted pending with no destination yet.

Revision ID: c4e91b7a3f56
Revises: 7b3f9a2e1c48
Create Date: 2026-09-09 12:11:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e91b7a3f56"
down_revision: str | None = "7b3f9a2e1c48"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("tx_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("debit_account_id", sa.Uuid(), nullable=True),
        sa.Column("credit_account_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("tx_id"),
        sa.ForeignKeyConstraint(["debit_account_id"], ["accounts.account_id"]),
        sa.ForeignKeyConstraint(["credit_account_id"], ["accounts.account_id"]),
        sa.CheckConstraint(
            "type IN ('deposit','treasury_purchase','remittance','fee','withdrawal')",
            name="transactions_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','failed')",
            name="transactions_status_valid",
        ),
        sa.CheckConstraint("amount > 0", name="transactions_amount_positive"),
    )


def downgrade() -> None:
    op.drop_table("transactions")
