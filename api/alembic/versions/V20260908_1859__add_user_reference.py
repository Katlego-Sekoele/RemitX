"""add user reference

Adds `first_name` and `reference` to `users` (Transaction_Flow_Context.md
Phase A): `reference` is the sender's permanent EFT payment reference —
`first_name`'s lowercase, <=8-char prefix plus a number disambiguating
same-named senders (e.g. "sian1") — generated once at signup by
`UserRepository.next_reference`. Deposits are no longer registered in-app;
`reference` is what lets the daily bank-statement reconciliation job
attribute an incoming payment to a user. See deposit_service.

Revision ID: 3f5a3361ea7c
Revises: cb7d0365d3f7
Create Date: 2026-09-08 18:59:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f5a3361ea7c"
down_revision: str | None = "cb7d0365d3f7"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.Text(), nullable=True))
    # No existing rows can carry a real reference yet, so there's nothing to
    # backfill — added straight to NOT NULL UNIQUE.
    op.add_column("users", sa.Column("reference", sa.Text(), nullable=False))
    op.create_index(op.f("ix_users_reference"), "users", ["reference"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_reference"), table_name="users")
    op.drop_column("users", "reference")
    op.drop_column("users", "first_name")
