"""add user profile fields

Adds `first_name`, `base_reference`, `role`, and `kyc_status` to `users`.

`base_reference` (e.g. "sian1") is a user's permanent, disambiguated name —
not itself an EFT-matchable reference; each of the user's currency accounts
builds its own reference by appending a currency suffix to it, once the
accounts model lands. `role`/`kyc_status` gate admin actions and KYC status.

Revision ID: a1c5e08f3d67
Revises: cb7d0365d3f7
Create Date: 2026-09-10 09:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1c5e08f3d67"
down_revision: str | None = "cb7d0365d3f7"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.Text(), nullable=True))
    # No existing rows can carry a real base_reference yet, so there's
    # nothing to backfill — added straight to NOT NULL UNIQUE.
    op.add_column("users", sa.Column("base_reference", sa.Text(), nullable=False))
    op.create_index(
        op.f("ix_users_base_reference"), "users", ["base_reference"], unique=True
    )
    op.add_column(
        "users",
        sa.Column("role", sa.Text(), nullable=False, server_default="user"),
    )
    op.add_column(
        "users",
        sa.Column("kyc_status", sa.Text(), nullable=False, server_default="UNVERIFIED"),
    )
    op.create_check_constraint("users_role_valid", "users", "role IN ('user', 'admin')")
    op.create_check_constraint(
        "users_kyc_status_valid", "users", "kyc_status IN ('UNVERIFIED', 'APPROVED')"
    )


def downgrade() -> None:
    op.drop_constraint("users_kyc_status_valid", "users", type_="check")
    op.drop_constraint("users_role_valid", "users", type_="check")
    op.drop_column("users", "kyc_status")
    op.drop_column("users", "role")
    op.drop_index(op.f("ix_users_base_reference"), table_name="users")
    op.drop_column("users", "base_reference")
    op.drop_column("users", "first_name")
