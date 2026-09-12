"""add user_roles grant record

Role administration (#53) turns ``user_roles`` from a join table into the
record of who was given what, by whom, and why. Everything added here is a
new nullable column or a boolean backfilled to false, so the running API —
which does not read any of it — keeps serving against the new schema during
the rolling update (alembic/README.md, rule 5).

The two booleans land with a server default so the existing rows can be NOT
NULL, and then have it dropped: the ORM sets both in Python, and leaving a
default behind would show up as drift in ``alembic check``.

Revision ID: e58b1c740a92
Revises: 916c56a3b1f9
Create Date: 2026-09-12 22:00:00.000000+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e58b1c740a92"
down_revision: str | None = "916c56a3b1f9"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.add_column("user_roles", sa.Column("grant_reason", sa.Text(), nullable=True))
    op.add_column(
        "user_roles",
        sa.Column(
            "self_granted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("user_roles", "self_granted", server_default=None)
    op.add_column(
        "user_roles",
        sa.Column(
            "toxic_combination_acknowledged",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column(
        "user_roles",
        "toxic_combination_acknowledged",
        server_default=None,
    )
    op.add_column("user_roles", sa.Column("revoked_by", sa.Uuid(), nullable=True))
    op.add_column("user_roles", sa.Column("revoke_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_user_roles_revoked_by_users",
        "user_roles",
        "users",
        ["revoked_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_user_roles_revoked_by_users",
        "user_roles",
        type_="foreignkey",
    )
    op.drop_column("user_roles", "revoke_reason")
    op.drop_column("user_roles", "revoked_by")
    op.drop_column("user_roles", "toxic_combination_acknowledged")
    op.drop_column("user_roles", "self_granted")
    op.drop_column("user_roles", "grant_reason")
