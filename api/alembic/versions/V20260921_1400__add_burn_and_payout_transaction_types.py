"""add burn and payout transaction types

Gates a remittance's beneficiary payout on a real on-chain burn
(Transaction_Flow_Context.md §2 Phase C, "Planned" note): `confirm_remittance`
now inserts a 7th leg (`type='token_burn'`, treasury -> UCTUSD issuer) and renames
the payout leg's `type` from `remittance` to `beneficiary_payout`, so
`remitx_worker.tasks.burn_treasury_tokens` can address each on its own.
`status='processing'` is the claim state a burn leg sits in between being
picked up and its XRPL `Payment` resolving. `xrpl_tx_hash` records that
payment's validated hash once it lands.

All additive — existing rows and code keep working unchanged.

Revision ID: 2f96c6fad117
Revises: f91d979fecaf
Create Date: 2026-09-21 14:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2f96c6fad117"
down_revision: str | None = "f91d979fecaf"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.drop_constraint("transactions_type_valid", "transactions", type_="check")
    op.create_check_constraint(
        "transactions_type_valid",
        "transactions",
        "type IN ('deposit','treasury_funding','remittance','fee','withdrawal',"
        "'token_burn','beneficiary_payout')",
    )
    op.drop_constraint("transactions_status_valid", "transactions", type_="check")
    op.create_check_constraint(
        "transactions_status_valid",
        "transactions",
        "status IN ('pending','processing','confirmed','failed')",
    )
    op.add_column("transactions", sa.Column("xrpl_tx_hash", sa.Text(), nullable=True))
    op.create_index(
        "ix_transactions_xrpl_tx_hash", "transactions", ["xrpl_tx_hash"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_transactions_xrpl_tx_hash", table_name="transactions")
    op.drop_column("transactions", "xrpl_tx_hash")
    op.drop_constraint("transactions_status_valid", "transactions", type_="check")
    op.create_check_constraint(
        "transactions_status_valid",
        "transactions",
        "status IN ('pending','confirmed','failed')",
    )
    op.drop_constraint("transactions_type_valid", "transactions", type_="check")
    op.create_check_constraint(
        "transactions_type_valid",
        "transactions",
        "type IN ('deposit','treasury_funding','remittance','fee','withdrawal')",
    )
