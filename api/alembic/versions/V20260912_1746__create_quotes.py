"""create quotes

The frozen price shown to a customer for a remittance
(Transaction_Flow_Context.md §2 Phase B, §3). See models/orm/quote.py.

Revision ID: 9b2e7c5a1f43
Revises: 6d4b8f1a92c7
Create Date: 2026-09-12 17:46:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b2e7c5a1f43"
down_revision: str | None = "6d4b8f1a92c7"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("sender_account_id", sa.Uuid(), nullable=False),
        sa.Column("beneficiary_account_id", sa.Uuid(), nullable=False),
        sa.Column("sender_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("sender_currency", sa.Text(), nullable=False),
        sa.Column("sender_transaction_fee", sa.Numeric(20, 8), nullable=False),
        sa.Column("token_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("token_name", sa.Text(), nullable=False),
        sa.Column("fiat_to_token_exchange_rate_id", sa.Uuid(), nullable=True),
        sa.Column("fiat_to_token_exchange_rate", sa.Numeric(20, 8), nullable=False),
        sa.Column("fiat_exchange_rate_id", sa.Uuid(), nullable=False),
        sa.Column("fiat_exchange_rate", sa.Numeric(20, 8), nullable=False),
        sa.Column("exchange_rate_margin", sa.Numeric(20, 8), nullable=False),
        sa.Column("receiver_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("receiver_currency", sa.Text(), nullable=False),
        sa.Column("receiver_payout_fee", sa.Numeric(20, 8), nullable=False),
        sa.Column("receiver_payout_estimate", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="ACTIVE"),
        sa.PrimaryKeyConstraint("quote_id"),
        sa.ForeignKeyConstraint(["sender_account_id"], ["accounts.account_id"]),
        sa.ForeignKeyConstraint(["beneficiary_account_id"], ["accounts.account_id"]),
        sa.ForeignKeyConstraint(
            ["fiat_to_token_exchange_rate_id"], ["exchange_rates.id"]
        ),
        sa.ForeignKeyConstraint(["fiat_exchange_rate_id"], ["exchange_rates.id"]),
        sa.CheckConstraint(
            "status IN ('ACTIVE','USED','EXPIRED')", name="quotes_status_valid"
        ),
        sa.CheckConstraint("sender_amount > 0", name="quotes_sender_amount_positive"),
    )
    op.create_index("ix_quotes_sender_account_id", "quotes", ["sender_account_id"])


def downgrade() -> None:
    op.drop_index("ix_quotes_sender_account_id", table_name="quotes")
    op.drop_table("quotes")
