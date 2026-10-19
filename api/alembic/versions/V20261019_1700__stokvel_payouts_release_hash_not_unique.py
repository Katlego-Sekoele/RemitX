"""stokvel payouts: a release hash may be shared by rounds

Ticket R3-04. ``V20261016_1200`` made ``stokvel_payouts.release_tx_hash``
unique, but one ``contribute`` can release two rounds. The contract's
``_releaseDue`` releases every round that has become due, and a round is due
only once it and the next round are fully paid and its payout time has
passed. Rounds fill in order, so this releases two rounds in one transaction
in one case only: the cycle's final contribution, made after the last
round's payout time has passed. It then releases the second-last round (its
next round is now full) and the last (full, with no next round). Rare on a
normal schedule, but likely in a demo whose dates are close together or past.
Both payouts carry the same hash, and the second would be refused: its
``RoundFinalised`` held as failed on every sync run, and the cycle never
closed.

``uq_stokvel_payouts_cycle_id_round`` already stops a round being recorded
twice, so the hash needs no constraint of its own. Dropping a unique constraint
only allows more, so it is safe against the code already running (rule 5).

Revision ID: 8c4f2a6d1e93
Revises: 5b1e7c2d9a40
Create Date: 2026-10-19 17:00:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8c4f2a6d1e93"
down_revision: str | None = "5b1e7c2d9a40"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

# Postgres's default name for the unnamed UniqueConstraint("release_tx_hash")
_CONSTRAINT = "stokvel_payouts_release_tx_hash_key"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "stokvel_payouts", type_="unique")


def downgrade() -> None:
    # Fails if two payouts already share a release hash, which is what this
    # revision allows: those rows would have to be changed first.
    op.create_unique_constraint(_CONSTRAINT, "stokvel_payouts", ["release_tx_hash"])
