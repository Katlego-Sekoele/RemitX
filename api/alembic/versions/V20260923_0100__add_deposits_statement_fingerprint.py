"""add deposits statement fingerprint

A bank-statement line is identified by its UTC date, reference and amount.
Uploading the same CSV twice, or an overlapping range, must not credit the
balance again. Existing rows are fingerprinted from the transaction already
stored for them. Where that identity collides (the bug this closes), the
earliest row keeps it and the extras get a legacy key so the money already
credited is left in place.

Revision ID: a7c3e91b4d20
Revises: b4e8c1a09f62
Create Date: 2026-09-23 01:00:00.000000+00:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c3e91b4d20"
down_revision: str | None = "b4e8c1a09f62"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_CONSTRAINT = "uq_deposits_statement_fingerprint"


def upgrade() -> None:
    op.execute("ALTER TABLE deposits ADD COLUMN statement_fingerprint TEXT")
    op.execute(
        """
        UPDATE deposits AS d
        SET statement_fingerprint = (
            SELECT to_char(t.created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD')
                || '|'
                || COALESCE(btrim(d.user_account_reference), '')
                || '|'
                || to_char(t.amount, 'FM9999999999999990.00')
            FROM transactions AS t
            WHERE t.tx_id = d.tx_id
        )
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT d.deposit_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY d.statement_fingerprint
                       ORDER BY t.created_at, d.deposit_id
                   ) AS position
            FROM deposits AS d
            JOIN transactions AS t ON t.tx_id = d.tx_id
        )
        UPDATE deposits
        SET statement_fingerprint = 'legacy:' || deposit_id
        WHERE deposit_id IN (
            SELECT deposit_id FROM ranked WHERE position > 1
        )
        """
    )
    op.execute(
        "ALTER TABLE deposits ALTER COLUMN statement_fingerprint SET NOT NULL"
    )
    op.create_unique_constraint(_CONSTRAINT, "deposits", ["statement_fingerprint"])


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "deposits", type_="unique")
    op.drop_column("deposits", "statement_fingerprint")
