"""backfill quotes.sender_amount_zar

Every existing quote gets its rand value. A ZAR quote is worth its own amount.
Every quote before this migration was ZAR (`create_quote` refused any other
sender currency until this same change lifted it), so that covers them all;
the other branch — valuing a non-ZAR quote through the USD peg it stored
(`fiat_to_token_exchange_rate`, USD per unit) at the USD/ZAR rate in force
when it was quoted, the last one fetched before it or else the first after —
is there for whatever a future direct write or a bypassed check leaves NULL,
not because any row needs it today.

Downgrading clears the column again, the state the previous migration leaves
it in; reads then fall back to `sender_amount`.

Revision ID: 808c8537c67b
Revises: 46b798718ccd
Create Date: 2026-09-26 17:51:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "808c8537c67b"
down_revision: str | None = "46b798718ccd"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE quotes
        SET sender_amount_zar = sender_amount
        WHERE sender_currency = 'ZAR' AND sender_amount_zar IS NULL
        """
    )
    op.execute(
        """
        UPDATE quotes AS q
        SET sender_amount_zar = ROUND(
            q.sender_amount * q.fiat_to_token_exchange_rate * (
                SELECT r.rate
                FROM exchange_rates AS r
                WHERE r.base_currency = 'USD' AND r.quote_currency = 'ZAR'
                ORDER BY r.fetched_at > q.created_at,
                    ABS(EXTRACT(EPOCH FROM r.fetched_at - q.created_at))
                LIMIT 1
            ),
            2
        )
        WHERE q.sender_currency <> 'ZAR' AND q.sender_amount_zar IS NULL
        """
    )


def downgrade() -> None:
    op.execute("UPDATE quotes SET sender_amount_zar = NULL")
