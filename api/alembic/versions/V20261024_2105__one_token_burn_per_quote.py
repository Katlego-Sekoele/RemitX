"""one token burn leg per quote

Ticket R3-08. ``transactions`` has no round column, so UNIQUE (round, type)
cannot live here. A stokvel round already has one payout
(``uq_stokvel_payouts_cycle_id_round``) and that payout has one quote. The
burn leg is the ``token_burn`` row on that quote. A second insert is the
double burn a retried payout must not record. A failed burn stays on the
same row; another attempt is a new quote.

The index is partial: a quote's other legs (two ``remittance`` rows, the
payout) share ``quote_id``. NULL ``quote_id`` values are distinct in a
unique index, so the CHECK forces every burn to name its quote. Adding
both only refuses more rows. The code already running writes a quote on
every burn, so this is safe against it (rule 5). The migration fails if a
quote already has two burns, or a burn has no quote; neither should.

Revision ID: a91c4e7b2d08
Revises: f4a8c2e91b03
Create Date: 2026-10-24 21:05:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a91c4e7b2d08"
down_revision: str | None = "f4a8c2e91b03"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_index(
        "uq_transactions_one_token_burn_per_quote",
        "transactions",
        ["quote_id"],
        unique=True,
        postgresql_where=sa.text("type = 'token_burn'"),
        sqlite_where=sa.text("type = 'token_burn'"),
    )
    op.create_check_constraint(
        "transactions_token_burn_has_quote",
        "transactions",
        "type <> 'token_burn' OR quote_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "transactions_token_burn_has_quote", "transactions", type_="check"
    )
    op.drop_index(
        "uq_transactions_one_token_burn_per_quote",
        table_name="transactions",
    )
