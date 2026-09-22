"""add users last_name, mobile_number, country

None of these are resolved/settable from anywhere yet (no onboarding/profile
flow exists) — always NULL until one is built. Added so BeneficiaryController
can join a beneficiary's details from here instead of storing a second,
driftable copy on `beneficiaries` (see models/orm/beneficiary.py).

Revision ID: 393879e988d7
Revises: 9b2e7c5a1f43
Create Date: 2026-09-12 21:02:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "393879e988d7"
down_revision: str | None = "9b2e7c5a1f43"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mobile_number", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("country", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "country")
    op.drop_column("users", "mobile_number")
    op.drop_column("users", "last_name")
