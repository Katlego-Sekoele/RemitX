"""add quotes.sender_amount_zar

A quote's value in rand at its own rates: what it counts as against the
sending limits, which are in rand whatever account the money leaves.

Nullable for now, because the code already running when this applies writes
quotes without it (rule 5 in alembic/README.md). The next migration backfills
the rows that exist, reads fall back to `sender_amount` for any NULL left
behind (only ever a ZAR quote), and a later migration can make it NOT NULL.

Revision ID: 46b798718ccd
Revises: b3a8c1d4e5f6
Create Date: 2026-09-26 17:50:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "46b798718ccd"
down_revision: str | None = "b3a8c1d4e5f6"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column(
            "sender_amount_zar", sa.Numeric(precision=20, scale=8), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("quotes", "sender_amount_zar")
