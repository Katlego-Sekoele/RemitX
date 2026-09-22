"""add users full name

`users.full_name` holds the verified name from the user's latest approved KYC
application, and `users.country` (added earlier, never written until now) its
residential country. Both are copied at approval from here on, so a sender's
beneficiary list can show them: row-level security keeps a customer route out
of anyone else's `kyc_applications` row.

Backfills users approved before this migration from the application their
latest approval decided. Runs with the RLS GUCs empty, so every application is
visible.

Revision ID: 8d2f6b1c4a7e
Revises: 2f96c6fad117
Create Date: 2026-09-22 09:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d2f6b1c4a7e"
down_revision: str | None = "2f96c6fad117"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE users
        SET full_name = COALESCE(NULLIF(TRIM(latest.full_name), ''), users.full_name),
            country = COALESCE(latest.residential_country, users.country)
        FROM (
            SELECT DISTINCT ON (a.user_id)
                a.user_id, a.full_name, a.residential_country
            FROM kyc_decisions d
            JOIN kyc_applications a ON a.application_id = d.application_id
            WHERE d.decision = 'approved'
            ORDER BY a.user_id, d.decided_at DESC
        ) AS latest
        WHERE users.id = latest.user_id
        """
    )


def downgrade() -> None:
    # `country` stays: it predates this migration, which only started
    # writing it.
    op.drop_column("users", "full_name")
