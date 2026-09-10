"""add user profile fields

Adds `first_name`, `base_reference`, `role`, and `kyc_status` to `users`.

Supersedes the deleted V20260908_1859__add_user_reference.py — that
migration added `first_name`/`reference`; `reference` has since moved to
`accounts` (Transaction_Flow_Context.md §1, per an account-per-currency
model). `base_reference` (e.g. "sian1") replaces it here: the shared prefix
every one of a user's account references is built from, but not itself an
EFT-matchable reference — see models/orm/user.py.

`role`/`kyc_status` were already on the ORM model (added for
Transaction_Flow_Context.md's admin/KYC gating) but were never actually
migrated — folding that fix in here since this exact spot in the chain is
already being touched.

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
