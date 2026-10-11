"""backfill transactions.evm_tx_hash

Copies every burn hash recorded so far from ``xrpl_tx_hash`` into
``evm_tx_hash`` (added by the previous migration), so reads of the new
column see the whole history.

Downgrading clears the column again, the state the previous migration leaves
it in. Nothing is lost: every hash is still in ``xrpl_tx_hash``.

Revision ID: 45ec46232228
Revises: 0c4f46c5868e
Create Date: 2026-10-11 10:03:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "45ec46232228"
down_revision: str | None = "0c4f46c5868e"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE transactions
        SET evm_tx_hash = xrpl_tx_hash
        WHERE xrpl_tx_hash IS NOT NULL AND evm_tx_hash IS NULL
        """
    )


def downgrade() -> None:
    op.execute("UPDATE transactions SET evm_tx_hash = NULL")
