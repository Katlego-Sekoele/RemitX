"""create bank_accounts and withdrawals

The withdrawal flow: a user's external bank account (`bank_accounts`,
Transaction_Flow_Context.md §2 Phase E's `bank_acc_id`, never previously
built) and the withdrawal request itself (`withdrawals`, lean like
`remittances` — status lives on the linked `transactions` rows). See
services/withdrawal_service.py and services/bank_account_service.py.

All additive — new tables only.

Revision ID: 9b1353b0faa4
Revises: a77cbaf94587
Create Date: 2026-09-22 10:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b1353b0faa4"
down_revision: str | None = "a77cbaf94587"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "bank_accounts",
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("account_holder_name", sa.Text(), nullable=False),
        sa.Column("bank_name", sa.Text(), nullable=False),
        sa.Column("account_number", sa.Text(), nullable=False),
        sa.Column("branch_code", sa.Text(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="pending_verification",
        ),
        sa.Column("verified_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("bank_account_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["verified_by_admin_id"], ["users.id"]),
        sa.CheckConstraint(
            "status IN ('pending_verification','verified','rejected')",
            name="bank_accounts_status_valid",
        ),
    )
    op.create_index(
        "ix_bank_accounts_user_id", "bank_accounts", ["user_id"], unique=False
    )

    op.create_table(
        "withdrawals",
        sa.Column("withdrawal_id", sa.Uuid(), nullable=False),
        sa.Column("tx_id", sa.Uuid(), nullable=False),
        sa.Column("fee_tx_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("bank_account_id", sa.Uuid(), nullable=False),
        sa.Column("gross_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("fee_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("net_amount", sa.Numeric(20, 8), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("confirmed_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("withdrawal_id"),
        sa.ForeignKeyConstraint(["tx_id"], ["transactions.tx_id"]),
        sa.ForeignKeyConstraint(["fee_tx_id"], ["transactions.tx_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.bank_account_id"]),
    )
    op.create_index("ix_withdrawals_user_id", "withdrawals", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_withdrawals_user_id", table_name="withdrawals")
    op.drop_table("withdrawals")
    op.drop_index("ix_bank_accounts_user_id", table_name="bank_accounts")
    op.drop_table("bank_accounts")
