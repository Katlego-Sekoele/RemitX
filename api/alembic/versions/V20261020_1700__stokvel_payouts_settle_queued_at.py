"""stokvel payouts: when the payout was last queued

Ticket R3-05 (#242 review). ``stokvel_payouts.settle_queued_at`` records when
the event sync last queued ``stokvel.settle_payout`` for a released payout, so
it queues the payout again only some minutes later. It used ``updated_at``
for this, which any other write to the row also moves, so an Administrator
action could delay a payout. A new nullable column, so safe against the code
already running (rule 5).

Revision ID: 3e7b9d2c4a51
Revises: 8c4f2a6d1e93
Create Date: 2026-10-20 17:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3e7b9d2c4a51"
down_revision: str | None = "8c4f2a6d1e93"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column(
        "stokvel_payouts",
        sa.Column("settle_queued_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stokvel_payouts", "settle_queued_at")
