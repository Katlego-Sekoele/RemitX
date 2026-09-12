"""add roles grant policy flags

Which role is implicit and which must never lose its last holder were role
names compared inside the role-administration controller. They are facts
about the catalogue, so they move into it: an operator can mark a new role
non-grantable, or protect a second role against emptying out, without a
build and a deploy.

Both land with a server default so the existing rows can be NOT NULL, and
then have it dropped — the ORM sets both in Python, and a default left behind
shows up as drift in ``alembic check``. Same shape as ``roles.is_admin``
(c3a91f5e82b1).

Revision ID: f1d47a0c3b58
Revises: e58b1c740a92
Create Date: 2026-09-12 23:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.rbac_seed import (
    ROLE_SEEDS,
    precompute_role_id_given_role_name,
)

# revision identifiers, used by Alembic.
revision: str = "f1d47a0c3b58"
down_revision: str | None = "e58b1c740a92"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "is_grantable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column("roles", "is_grantable", server_default=None)
    op.add_column(
        "roles",
        sa.Column(
            "protect_last_holder",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("roles", "protect_last_holder", server_default=None)

    connection = op.get_bind()
    for role in ROLE_SEEDS:
        connection.execute(
            sa.text(
                "UPDATE roles SET is_grantable = :is_grantable, "
                "protect_last_holder = :protect_last_holder WHERE role_id = :role_id"
            ),
            {
                "is_grantable": role.is_grantable,
                "protect_last_holder": role.protect_last_holder,
                "role_id": precompute_role_id_given_role_name(role.name),
            },
        )


def downgrade() -> None:
    op.drop_column("roles", "protect_last_holder")
    op.drop_column("roles", "is_grantable")
