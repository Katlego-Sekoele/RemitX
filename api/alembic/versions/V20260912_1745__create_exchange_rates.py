"""create exchange_rates

Fetched FX rates (Transaction_Flow_Context.md §4). Only USD->ZAR is ever
populated for now — see models/orm/exchange_rate.py.

Revision ID: 6d4b8f1a92c7
Revises: a3f6c1d9e274
Create Date: 2026-09-12 17:45:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d4b8f1a92c7"
down_revision: str | None = "a3f6c1d9e274"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("base_currency", sa.Text(), nullable=False),
        sa.Column("quote_currency", sa.Text(), nullable=False),
        sa.Column("rate", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exchange_rates_valid_until", "exchange_rates", ["valid_until"])


def downgrade() -> None:
    op.drop_index("ix_exchange_rates_valid_until", table_name="exchange_rates")
    op.drop_table("exchange_rates")
