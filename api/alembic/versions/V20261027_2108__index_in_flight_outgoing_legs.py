"""index in-flight outgoing legs

Revision ID: 09149682d0b2
Revises: 9d2834001cc7
Create Date: 2026-10-27 21:08:12.586236+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "09149682d0b2"
down_revision: str | None = "9d2834001cc7"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.create_index(
        "ix_transactions_credit_inflight",
        "transactions",
        ["credit_account_id"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
        sqlite_where=sa.text("status IN ('pending', 'processing')"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transactions_credit_inflight",
        table_name="transactions",
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
        sqlite_where=sa.text("status IN ('pending', 'processing')"),
    )
