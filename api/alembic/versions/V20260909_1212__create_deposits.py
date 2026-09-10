"""create deposits

ZAR cash-in header (Transaction_Flow_Context.md Phase A). `deposits` was
never migrated before this — the prior model existed only in the ORM, so
this is a fresh create, not an expand/contract of a live table.

Revision ID: f28d4a6e9c13
Revises: c4e91b7a3f56
Create Date: 2026-09-09 12:12:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f28d4a6e9c13"
down_revision: str | None = "c4e91b7a3f56"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "deposits",
        sa.Column("deposit_id", sa.Uuid(), nullable=False),
        sa.Column("tx_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("user_reference", sa.Text(), nullable=True),
        sa.Column("payment_method", sa.Text(), nullable=False),
        sa.Column("confirmed_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("deposit_id"),
        sa.ForeignKeyConstraint(["tx_id"], ["transactions.tx_id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    )
    op.create_index("ix_deposits_user_id", "deposits", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_deposits_user_id", table_name="deposits")
    op.drop_table("deposits")
