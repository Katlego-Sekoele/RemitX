"""stokvel cycle on-chain registration

Ticket R2-10. Starting a cycle (``POST /stokvels/{id}/cycles``) makes it
``active`` in the database at once, and the worker then registers it on the
contract (``createStokvel`` for a new stokvel, then ``startCycle``). Until
``startCycle`` is mined the contract knows no open cycle, so a contribution
sent then would revert. These columns record the registration, and the
contribution API refuses contributions until ``registered_at`` is set:

- ``start_tx_hash``: the ``startCycle`` transaction, stored after signing and
  before the send, so a redelivered task waits on it instead of sending again
- ``start_block_number``: the block it was mined in
- ``registered_at``: when the worker recorded the cycle as open on-chain. It
  may be set without a hash or block, when the worker finds the cycle already
  started on-chain (the hash of a lost delivery)

A ``forming`` cycle has none of them. All three are new nullable columns, so
the change is additive and safe against the release already running (README
rule 5). Customers cannot read or write them any differently: the cycle's
existing row-level security applies.

Revision ID: 9ecf9bd5e4bc
Revises: 5b1e7c2d9a40
Create Date: 2026-10-19 10:51:35.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ecf9bd5e4bc"
down_revision: str | None = "5b1e7c2d9a40"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_TABLE = "stokvel_cycles"
_CHECKS = {
    "stokvel_cycles_forming_not_registered": (
        "status <> 'forming' OR (start_tx_hash IS NULL AND registered_at IS NULL)"
    ),
    "stokvel_cycles_start_block_is_registered": (
        "start_block_number IS NULL OR registered_at IS NOT NULL"
    ),
    "stokvel_cycles_start_block_nonneg": (
        "start_block_number IS NULL OR start_block_number >= 0"
    ),
}
_UNIQUE = "stokvel_cycles_start_tx_hash_key"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("start_tx_hash", sa.Text(), nullable=True))
    op.add_column(
        _TABLE, sa.Column("start_block_number", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        _TABLE, sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(_UNIQUE, _TABLE, ["start_tx_hash"])
    for name, condition in _CHECKS.items():
        op.create_check_constraint(name, _TABLE, condition)


def downgrade() -> None:
    for name in reversed(_CHECKS):
        op.drop_constraint(name, _TABLE, type_="check")
    op.drop_constraint(_UNIQUE, _TABLE, type_="unique")
    op.drop_column(_TABLE, "registered_at")
    op.drop_column(_TABLE, "start_block_number")
    op.drop_column(_TABLE, "start_tx_hash")
