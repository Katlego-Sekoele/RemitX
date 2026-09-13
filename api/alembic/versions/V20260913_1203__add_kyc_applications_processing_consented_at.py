"""add kyc applications processing consented at

Records when the applicant consented, on review, to RemitX processing the
application for FICA due diligence. Distinct from `submitted_at`, which is the
first time the application entered review and is never moved.

Revision ID: d7b1e4c82a19
Revises: bfcc9109c5c2
Create Date: 2026-09-13 10:03:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

revision: str = "d7b1e4c82a19"
down_revision: str | None = "bfcc9109c5c2"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.add_column(
            sa.Column("processing_consented_at", sa.DateTime(timezone=True))
        )


def downgrade() -> None:
    with op.batch_alter_table("kyc_applications") as batch_op:
        batch_op.drop_column("processing_consented_at")
