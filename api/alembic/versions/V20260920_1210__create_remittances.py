"""create remittances

A confirmed send (Transaction_Flow_Context.md §2 Phase B2). See
models/orm/remittance.py for why this is deliberately lean — `Quote` already
freezes every priced field.

Also adds the `transactions.quote_id -> quotes.quote_id` FK: `quotes` didn't
exist yet when `transactions` was created, so the column was left
unconstrained. It's the grouping key `settle_remittance` guards its batch
update on, so it's worth being a real FK now that `quotes` exists.

Revision ID: c04384f03c5a
Revises: f35202d9c724
Create Date: 2026-09-20 12:10:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c04384f03c5a"
down_revision: str | None = "f35202d9c724"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "remittances",
        sa.Column("remittance_id", sa.Uuid(), nullable=False),
        sa.Column("quote_id", sa.Uuid(), nullable=False),
        sa.Column("tx_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("remittance_id"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.quote_id"]),
        sa.ForeignKeyConstraint(["tx_id"], ["transactions.tx_id"]),
        sa.UniqueConstraint("quote_id", name="remittances_quote_id_unique"),
    )
    op.create_foreign_key(
        "fk_transactions_quote_id_quotes",
        "transactions",
        "quotes",
        ["quote_id"],
        ["quote_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_transactions_quote_id_quotes", "transactions", type_="foreignkey"
    )
    op.drop_table("remittances")
