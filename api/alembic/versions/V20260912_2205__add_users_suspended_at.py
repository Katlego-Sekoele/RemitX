"""add users suspended_at

Compliance's "stop this account" switch (`user:suspend`), kept off the KYC
state machine on purpose: a suspended user may well be KYC-approved, and
lifting the suspension should not have to reconstruct where their application
had got to.

Additive and nullable, so it is safe against the app version already running
(alembic/README.md rule 5).

Revision ID: 2b4f7c1a9e05
Revises: 1112727332b0
Create Date: 2026-09-12 22:05:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b4f7c1a9e05"
down_revision: str | None = "1112727332b0"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "suspended_at")
