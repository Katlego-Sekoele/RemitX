"""add transactions.evm_tx_hash

Ticket R3-02 (#239): the system moves from the XRP Ledger to the XRPL EVM
chain (D1), so ``xrpl_tx_hash`` is renamed ``evm_tx_hash``.

A rename in one step would break the worker already running, which writes
``xrpl_tx_hash`` after a burn lands on chain (rule 5 in alembic/README.md).
So this is the expand step: add ``evm_tx_hash`` beside it. The new code
writes both and reads ``evm_tx_hash``; the next migration copies the
existing hashes across. A later migration copies any hash written only to
``xrpl_tx_hash`` while the rollout ran, then drops it.

Revision ID: 0c4f46c5868e
Revises: 7895afbbf058
Create Date: 2026-10-11 10:02:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0c4f46c5868e"
down_revision: str | None = "7895afbbf058"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("evm_tx_hash", sa.Text(), nullable=True))
    op.create_index(
        op.f("ix_transactions_evm_tx_hash"),
        "transactions",
        ["evm_tx_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transactions_evm_tx_hash"), table_name="transactions")
    op.drop_column("transactions", "evm_tx_hash")
