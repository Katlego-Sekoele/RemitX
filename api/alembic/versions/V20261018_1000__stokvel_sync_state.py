"""stokvel sync state and held events

Ticket R2-13. The event sync's tables (doc section 3):

- ``stokvel_sync_state``: the cursor, one row per contract address, with the
  last block whose events have been applied
- ``stokvel_held_events``: events the sync could not apply yet, so it moves
  past them without losing them: ``waiting`` for something that does not
  exist yet (the release task), or ``failed`` for a person. Retried on every
  run

Worker-only: row-level security admits only sessions with no customer bound
(the worker, migrations), so no customer route can read or change either.

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

_UNBOUND = "COALESCE(current_setting('app.current_user_id', true), '') = ''"
_TABLES = ("stokvel_sync_state", "stokvel_held_events")


def _worker_only(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_worker_only ON {table}
          USING ({_UNBOUND})
          WITH CHECK ({_UNBOUND})
        """
    )


def upgrade() -> None:
    op.create_table(
        "stokvel_sync_state",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("last_processed_block", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "last_processed_block >= 0", name="stokvel_sync_state_block_nonneg"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "stokvel_held_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contract_address", sa.Text(), nullable=False),
        sa.Column("tx_hash", sa.Text(), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("raw_log", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "reason IN ('waiting', 'failed')",
            name="stokvel_held_events_reason_valid",
        ),
        sa.CheckConstraint(
            "args IS NOT NULL OR raw_log IS NOT NULL",
            name="stokvel_held_events_has_event",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "contract_address",
            "tx_hash",
            "log_index",
            name="uq_stokvel_held_events_log",
        ),
    )
    for table in _TABLES:
        _worker_only(table)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_worker_only ON {table}")
        op.drop_table(table)
