"""stokvel contribution legs and rand value

``stokvel_contributions`` (ticket R2-11): the contribution row now points at
its own ledger legs, so ``transactions`` needs no grouping column (agreed with
R3-01's owner, doc section 8):

- ``fiat_tx_id``: member's fiat account -> RemitX bank account
- ``token_tx_id``: Treasury Wallet -> the stokvel's ``STOKVEL`` account
- ``fee_tx_id``: member's fiat account -> RemitX fee revenue (null if no fee)

``amount_zar`` is the contribution plus its fee in rand, locked when it is
made, which counts against the member's own sending limits (D8).

All four are new nullable columns, so the change is additive and safe against
the release already running (README rule 5). ``tx_id`` is the first name of
``fiat_tx_id``; it is left in place, unused, for a later migration to drop,
rather than renamed here. Constraint names are Postgres's defaults, written out
so ``downgrade`` can drop them.

Revision ID: 86264fa21295
Revises: f02a457cc946
Create Date: 2026-10-16 13:52:04.864684+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "86264fa21295"
down_revision: str | None = "f02a457cc946"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_TABLE = "stokvel_contributions"
_LEG_COLUMNS = ("fiat_tx_id", "token_tx_id", "fee_tx_id")
_AMOUNT_ZAR_CHECK = "stokvel_contributions_amount_zar_positive"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("amount_zar", sa.Numeric(precision=20, scale=8), nullable=True),
    )
    op.create_check_constraint(
        _AMOUNT_ZAR_CHECK, _TABLE, "amount_zar IS NULL OR amount_zar > 0"
    )
    for column in _LEG_COLUMNS:
        op.add_column(_TABLE, sa.Column(column, sa.Uuid(), nullable=True))
        op.create_unique_constraint(f"{_TABLE}_{column}_key", _TABLE, [column])
        op.create_foreign_key(
            f"{_TABLE}_{column}_fkey", _TABLE, "transactions", [column], ["tx_id"]
        )


def downgrade() -> None:
    for column in reversed(_LEG_COLUMNS):
        op.drop_constraint(f"{_TABLE}_{column}_fkey", _TABLE, type_="foreignkey")
        op.drop_constraint(f"{_TABLE}_{column}_key", _TABLE, type_="unique")
        op.drop_column(_TABLE, column)
    op.drop_constraint(_AMOUNT_ZAR_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "amount_zar")
