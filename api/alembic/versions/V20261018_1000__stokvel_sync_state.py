"""stokvel sync state

Ticket R2-13. The event sync's cursor (doc section 3): one row per contract
address with the last block whose events have been applied.

Worker-only: row-level security admits only sessions with no customer bound
(the worker, migrations), as the stokvel tables do for their writes, so no
customer route can read or move the cursor.

Revision ID: 5b1e7c2d9a40
Revises: d9d228218faf
Create Date: 2026-10-18 10:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b1e7c2d9a40"
down_revision: str | None = "d9d228218faf"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None

_TABLE = "stokvel_sync_state"
_POLICY = "stokvel_sync_state_worker_only"
_UNBOUND = "COALESCE(current_setting('app.current_user_id', true), '') = ''"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("last_processed_block", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "last_processed_block >= 0", name="stokvel_sync_state_block_nonneg"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(f"ALTER TABLE {_TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {_TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {_POLICY} ON {_TABLE}
          USING ({_UNBOUND})
          WITH CHECK ({_UNBOUND})
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON {_TABLE}")
    op.drop_table(_TABLE)
