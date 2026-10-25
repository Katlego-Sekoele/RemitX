"""one token burn leg per quote

Ticket R3-08. ``transactions`` has no round column, so UNIQUE (round, type)
cannot live here. A stokvel round already has one payout
(``uq_stokvel_payouts_cycle_id_round``) and that payout has one quote. The
burn leg is the ``token_burn`` row on that quote. A second insert is the
double burn a retried payout must not record. A failed burn stays on the
same row; another attempt is a new quote.

The index is partial: a quote's other legs (two ``remittance`` rows, the
payout) share ``quote_id``. Adding it only refuses more rows, so it is
safe against the code already running (rule 5). It fails if a quote
already has two ``token_burn`` rows; none should.

No CHECK that ``quote_id`` is set. A unique index treats NULL as distinct,
but a burn recorded before this revision can have none: the EVM rename
test inserts one and then upgrades to head. A CHECK would stop that
upgrade.

Revision ID: a91c4e7b2d08
Revises: c5d91a7e2b40
Create Date: 2026-10-24 21:05:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a91c4e7b2d08"
down_revision: str | None = "c5d91a7e2b40"
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


def downgrade() -> None:
    op.drop_index(
        "uq_transactions_one_token_burn_per_quote",
        table_name="transactions",
    )
