"""drop users role

``users.role`` was a stopgap staff flag, added in a1c5e08f3d67 to gate admin
routes through the old ``auth.dependencies.require_admin``. The RBAC tables
(``user_roles`` -> ``role_permissions`` -> ``permissions``) replaced it two
days later, and the routes now gate on a ``PermissionCode`` through
``RequirePermission``. Nothing reads the column, so drop it rather than leave
a second, unsynchronised answer to "is this person staff" for the next caller
to reach for.

Postgres drops a single-column CHECK with its column, but the constraint is
dropped explicitly so the downgrade is a true mirror.

Revision ID: 916c56a3b1f9
Revises: 12cc69b78b1b
Create Date: 2026-09-12 17:38:01.170552+00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "916c56a3b1f9"
down_revision: str | None = "12cc69b78b1b"
branch_labels: str | tuple | None = None
depends_on: str | tuple | None = None


def upgrade() -> None:
    op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_valid"))
    op.drop_column("users", "role")


def downgrade() -> None:
    # NOT NULL on a table that already has rows, so the database needs its own
    # default — the same reason the original migration set one.
    op.add_column(
        "users",
        sa.Column("role", sa.Text(), nullable=False, server_default="user"),
    )
    op.create_check_constraint("users_role_valid", "users", "role IN ('user', 'admin')")
