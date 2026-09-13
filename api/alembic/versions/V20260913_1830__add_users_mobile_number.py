"""add users mobile number

The profile page's contact mobile. Not identity evidence: the verified mobile
stays on the approved `kyc_applications` row.

Revision ID: 63c9656baaa8
Revises: e5f81705ecd3
Create Date: 2026-09-13 18:30:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

revision: str = "63c9656baaa8"
down_revision: str | None = "e5f81705ecd3"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("mobile_number", sa.Text()))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("mobile_number")
