"""stokvel ledger account and transaction types

Ticket R3-01 (#238), decision D9 in docs/stokvel_integration.md: each stokvel
gets its own ledger account, type ``STOKVEL``, in the token. It holds a
released pool until the payout remittance sends it on.

- ``accounts_type_valid`` allows ``STOKVEL``. The owner and reference CHECKs
  need no change: a ``STOKVEL`` row has no user and no reference, which both
  already allow for any type but ``USER``.
- ``accounts_stokvel_balance_nonneg``: a stokvel pays out only what its
  members put in, so its balance never goes below zero.
- ``transactions_type_valid`` allows ``stokvel_contribution`` and
  ``stokvel_pool_release``. ``stokvel_refund`` is not added: refunds are out
  of scope for v1 (#208).
- ``stokvels.account_id`` links a stokvel to its account. Nullable, as the
  account is created after the stokvel row.

All additive: existing rows and the code already running keep working.

The downgrade fails on its CHECKs if any ``STOKVEL`` account or stokvel
transaction exists, rather than deleting ledger history.

Revision ID: 4fb6bcc07236
Revises: b2e338d2fc43
Create Date: 2026-10-11 10:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4fb6bcc07236"
down_revision: str | None = "b2e338d2fc43"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.drop_constraint("accounts_type_valid", "accounts", type_="check")
    op.create_check_constraint(
        "accounts_type_valid",
        "accounts",
        "type IN ('USER','REMITX_FIAT','REMITX_XRPL_WALLET',"
        "'REMITX_REVENUE','EXTERNAL','STOKVEL')",
    )
    op.create_check_constraint(
        "accounts_stokvel_balance_nonneg",
        "accounts",
        "type <> 'STOKVEL' OR account_balance >= 0",
    )
    op.drop_constraint("transactions_type_valid", "transactions", type_="check")
    op.create_check_constraint(
        "transactions_type_valid",
        "transactions",
        "type IN ('deposit','treasury_funding','remittance','fee','withdrawal',"
        "'token_burn','beneficiary_payout','stokvel_contribution',"
        "'stokvel_pool_release')",
    )
    op.add_column("stokvels", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint("stokvels_account_id_key", "stokvels", ["account_id"])
    op.create_foreign_key(
        "stokvels_account_id_fkey",
        "stokvels",
        "accounts",
        ["account_id"],
        ["account_id"],
    )


def downgrade() -> None:
    op.drop_constraint("stokvels_account_id_fkey", "stokvels", type_="foreignkey")
    op.drop_constraint("stokvels_account_id_key", "stokvels", type_="unique")
    op.drop_column("stokvels", "account_id")
    op.drop_constraint("transactions_type_valid", "transactions", type_="check")
    op.create_check_constraint(
        "transactions_type_valid",
        "transactions",
        "type IN ('deposit','treasury_funding','remittance','fee','withdrawal',"
        "'token_burn','beneficiary_payout')",
    )
    op.drop_constraint("accounts_stokvel_balance_nonneg", "accounts", type_="check")
    op.drop_constraint("accounts_type_valid", "accounts", type_="check")
    op.create_check_constraint(
        "accounts_type_valid",
        "accounts",
        "type IN ('USER','REMITX_FIAT','REMITX_XRPL_WALLET',"
        "'REMITX_REVENUE','EXTERNAL')",
    )
