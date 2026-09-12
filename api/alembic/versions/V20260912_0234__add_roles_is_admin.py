"""add roles is_admin

Revision ID: c3a91f5e82b1
Revises: b7e2d4f81a06
Create Date: 2026-09-12 02:34:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op
from remitx_api.models.orm.rbac_seed import (
    ROLE_SEEDS,
    precompute_role_id_given_role_name,
)

revision: str = "c3a91f5e82b1"
down_revision: str | None = "b7e2d4f81a06"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column(
        "roles",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("roles", "is_admin", server_default=None)

    connection = op.get_bind()
    for role in ROLE_SEEDS:
        connection.execute(
            sa.text("UPDATE roles SET is_admin = :is_admin WHERE role_id = :role_id"),
            {
                "is_admin": role.is_admin,
                "role_id": precompute_role_id_given_role_name(role.name),
            },
        )


def downgrade() -> None:
    op.drop_column("roles", "is_admin")
