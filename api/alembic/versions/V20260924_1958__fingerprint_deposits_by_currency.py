"""fingerprint deposits by currency

A statement line now carries its currency, and the fingerprint that stops a
line being credited twice includes it: the same reference and amount on the
same day in two currencies are two lines. Each existing fingerprint gets its
own transaction's currency appended, so re-uploading a statement that was
already reconciled still finds every line. Legacy keys, the duplicates left
over from before fingerprints, stay as they are.

Downgrading strips the currency again, and fails on the unique constraint if
two lines by then differ only in currency.

Revision ID: d7ea832b9596
Revises: 9b1353b0faa4
Create Date: 2026-09-24 19:58:50.249006+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7ea832b9596"
down_revision: str | None = "9b1353b0faa4"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE deposits AS d
        SET statement_fingerprint = d.statement_fingerprint || '|' || t.currency
        FROM transactions AS t
        WHERE t.tx_id = d.tx_id
          AND d.statement_fingerprint NOT LIKE 'legacy:%'
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
        UPDATE deposits
        SET statement_fingerprint = regexp_replace(
            statement_fingerprint, '\|[^|]*$', ''
        )
        WHERE statement_fingerprint NOT LIKE 'legacy:%'
        """
    )
